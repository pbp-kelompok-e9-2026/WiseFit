from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.urls import reverse
from rest_framework.test import APIClient

from .access import ANALYZER_GROUP
from .models import CarbonEstimate, MaterialFactor
from .tests import OfflineTestCase, fallback_co2e

User = get_user_model()

BODY = {
    "name": "Oversized Cotton Shirt",
    "category": "shirt",
    "material": "cotton",
    "price": "300000",
    "estimated_wears": 24,
}


class CarbonApiTests(OfflineTestCase):
    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.user = User.objects.create_user("zidan", password="pw")
        self.other = User.objects.create_user("budi", password="pw")
        self.analyst = User.objects.create_user("sari", password="pw")
        self.analyst.groups.add(Group.objects.get_or_create(name=ANALYZER_GROUP)[0])
        self.list_url = reverse("carbon_api:estimates")
        self.factors_url = reverse("carbon_api:factors")
        self.client.force_login(self.user)

    def make(self, user, name="x", material="cotton", category="shirt", co2e="3.2"):
        return CarbonEstimate.objects.create(
            user=user, name=name, category=category, material=material,
            weight_kg=Decimal("0.25"), co2e_kg=Decimal(co2e),
        )

    # akses
    def test_anonymous_gets_401(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.list_url).status_code, 401)

    def test_analyzer_cannot_use_personal_endpoints(self):
        self.client.force_login(self.analyst)
        self.assertEqual(self.client.get(self.list_url).status_code, 403)
        self.assertEqual(self.client.post(self.list_url, BODY, format="json").status_code, 403)

    def test_regular_user_cannot_use_analyzer_endpoints(self):
        for name in ("analysis", "factors"):
            self.assertEqual(self.client.get(reverse(f"carbon_api:{name}")).status_code, 403)
        self.assertEqual(self.client.put(self.factors_url, {"materials": {"cotton": 25}}, format="json").status_code, 403)

    # CRUD
    def test_create_uses_category_weight_and_offline_estimate(self):
        resp = self.client.post(self.list_url, BODY, format="json")
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertEqual(data["weight_kg"], 0.25)
        self.assertEqual(data["co2e_kg"], float(fallback_co2e("cotton", Decimal("0.25"))))
        self.assertEqual(data["source"], "fallback")
        self.assertEqual(CarbonEstimate.objects.get().user, self.user)

    def test_create_rejects_invalid_input(self):
        resp = self.client.post(self.list_url, {**BODY, "weight_kg": -1, "estimated_wears": 0}, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(CarbonEstimate.objects.count(), 0)

    def test_list_filters_sorts_and_hides_other_users(self):
        self.make(self.user, "Linen Shirt", co2e="1.5")
        self.make(self.user, "Wool Jacket", "wool", "jacket", "4.0")
        self.make(self.other, "Secret Dress", "silk", "dress", "2")
        resp = self.client.get(self.list_url, {"sort": "co2e_desc"}).json()
        self.assertEqual([r["name"] for r in resp["results"]], ["Wool Jacket", "Linen Shirt"])
        self.assertEqual([r["bar_pct"] for r in resp["results"]], [100, 38])
        resp = self.client.get(self.list_url, {"material": "cotton"}).json()
        self.assertEqual([r["name"] for r in resp["results"]], ["Linen Shirt"])
        self.assertTrue(resp["filtered"])

    def test_other_users_estimate_is_404(self):
        theirs = self.make(self.other)
        url = reverse("carbon_api:estimate-detail", args=[theirs.pk])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.delete(url).status_code, 404)
        self.assertTrue(CarbonEstimate.objects.filter(pk=theirs.pk).exists())

    def test_update_recomputes_only_when_inputs_change(self):
        obj = CarbonEstimate.objects.get(pk=self.client.post(self.list_url, BODY, format="json").json()["id"])
        url = reverse("carbon_api:estimate-detail", args=[obj.pk])
        with mock.patch("carbon_footprint.serializers.compute_co2e", return_value=(Decimal("9.99"), "fallback")) as call:
            self.client.patch(url, {"name": "Renamed", "estimated_wears": 30}, format="json")
            call.assert_not_called()
            self.client.patch(url, {"price": "350000"}, format="json")
            self.assertEqual(call.call_count, 1)
            self.client.patch(url, {"weight_kg": "1.00"}, format="json")
            self.assertEqual(call.call_count, 2)
        obj.refresh_from_db()
        self.assertEqual(obj.co2e_kg, Decimal("9.99"))

    def test_delete_returns_204(self):
        obj = self.make(self.user)
        resp = self.client.delete(reverse("carbon_api:estimate-detail", args=[obj.pk]))
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(CarbonEstimate.objects.exists())

    # numbers dan preview
    def test_numbers_returns_stats(self):
        self.client.post(self.list_url, BODY, format="json")
        data = self.client.get(reverse("carbon_api:numbers")).json()
        self.assertEqual(data["stats"]["wears"], 24)
        self.assertEqual(data["stats"]["cost_per_wear"], 12500)
        self.assertEqual(data["item"]["name"], "Oversized Cotton Shirt")

    def test_numbers_empty(self):
        data = self.client.get(reverse("carbon_api:numbers")).json()
        self.assertIsNone(data["item"])
        self.assertIsNone(data["stats"])

    def test_preview_is_offline_and_does_not_save(self):
        resp = self.client.post(reverse("carbon_api:preview"), {**BODY, "weight_kg": 1}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["cost_per_wear"], 12500)
        self.assertEqual(CarbonEstimate.objects.count(), 0)

    def test_preview_rejects_bad_input(self):
        resp = self.client.post(reverse("carbon_api:preview"), {**BODY, "category": "spaceship"}, format="json")
        self.assertEqual(resp.status_code, 400)

    # analyzer
    def test_analysis_never_exposes_private_names(self):
        self.make(self.user, "Jaket Rahasia")
        self.client.force_login(self.analyst)
        resp = self.client.get(reverse("carbon_api:analysis"), {"material": "cotton"})
        self.assertEqual(resp.json()["analysis"]["total"], 1)
        self.assertNotIn("Rahasia", resp.content.decode())

    def test_factors_update_recalculate_and_reset(self):
        offline = self.make(self.user, co2e="1.00")
        offline.weight_kg = Decimal("2.00")
        offline.save()
        self.client.force_login(self.analyst)
        resp = self.client.put(self.factors_url, {"materials": {"cotton": 10}, "recalculate": True}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["recalculated"], 1)
        offline.refresh_from_db()
        self.assertEqual(offline.co2e_kg, Decimal("20.00"))
        self.assertTrue(next(m for m in resp.json()["materials"] if m["key"] == "cotton")["changed"])
        resp = self.client.post(reverse("carbon_api:factors-reset"))
        self.assertEqual(MaterialFactor.objects.count(), 0)
        self.assertEqual(resp.json()["message"], "Faktor dikembalikan ke nilai bawaan.")

    def test_factors_reject_invalid_values(self):
        self.client.force_login(self.analyst)
        for body in ({"materials": {"cotton": 0}}, {"materials": {"unobtainium": 5}}, {"categories": {"shirt": "abc"}}):
            self.assertEqual(self.client.put(self.factors_url, body, format="json").status_code, 400)
        self.assertEqual(MaterialFactor.objects.count(), 0)