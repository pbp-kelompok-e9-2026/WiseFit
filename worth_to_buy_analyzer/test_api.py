from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from .models import ClothingReference, PurchaseAnalysis
from .tests import DATA

ROOT = "/api/worth-to-buy/"


class WorthToBuyAPITests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("mobile_user", password="mobile-test-password")
        cls.other = get_user_model().objects.create_user("other_user", password="mobile-test-password")
        cls.analyzer = get_user_model().objects.create_user("mobile_analyzer", password="mobile-test-password")
        cls.analyzer.groups.add(Group.objects.get(name="Analyzer"))
        cls.admin = get_user_model().objects.create_superuser("mobile_admin", password="mobile-test-password")

    def setUp(self):
        self.client = APIClient()
        self.authenticate(self.user)

    def authenticate(self, user):
        token, _ = Token.objects.get_or_create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

    def create_analysis(self, **values):
        response = self.client.post(ROOT + "analyses/", {**DATA, **values}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        return response.data

    def reference_data(self, **values):
        return {
            "clothing_name": "Kemeja referensi", "category": "top", "price": "300000.00",
            "source_name": "Katalog resmi", "is_published": False, **values,
        }

    def test_anonymous_and_inactive_accounts_cannot_access_private_data(self):
        self.client.credentials()
        self.assertEqual(self.client.get(ROOT + "analyses/").status_code, 401)
        self.assertEqual(self.client.post(ROOT + "analyses/", DATA, format="json").status_code, 401)
        self.user.is_active = False
        self.user.save()
        self.authenticate(self.user)
        self.assertEqual(self.client.get(ROOT + "analyses/").status_code, 401)

    def test_api_accepts_existing_django_login_session(self):
        self.client.credentials()
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(ROOT + "analyses/").status_code, 200)
        self.assertEqual(self.client.post(ROOT + "analyses/", DATA, format="json").status_code, 201)

    def test_cookie_session_still_requires_csrf_for_changes(self):
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.user)
        response = client.post(ROOT + "analyses/", DATA, format="json")
        self.assertEqual(response.status_code, 403)
        self.assertFalse(PurchaseAnalysis.objects.exists())

    def test_crud_returns_calculated_results_and_preserves_money_precision(self):
        created = self.create_analysis(owner=self.other.pk, carbon_kg_co2e="999", decision="buy")
        pk = created["id"]
        self.assertEqual(created["price"], "300000.00")
        self.assertEqual(created["result"]["cost_per_wear"], "5000.00")
        self.assertEqual(created["result"]["purchase_score"], 100)
        self.assertEqual(created["result"]["recommendation"], "buy")
        item = PurchaseAnalysis.objects.get(pk=pk)
        self.assertEqual(item.owner, self.user)
        self.assertIsNone(item.carbon_kg_co2e)
        self.assertEqual(item.decision, "undecided")
        self.assertEqual(self.client.get(ROOT + "analyses/").data["count"], 1)
        self.assertEqual(self.client.get(f"{ROOT}analyses/{pk}/").status_code, 200)
        updated = self.client.put(f"{ROOT}analyses/{pk}/", {**DATA, "price": "600000"}, format="json")
        self.assertEqual(updated.status_code, 200, updated.data)
        self.assertEqual(updated.data["result"]["cost_per_wear"], "10000.00")
        self.assertEqual(self.client.delete(f"{ROOT}analyses/{pk}/").status_code, 204)
        self.assertFalse(PurchaseAnalysis.objects.filter(pk=pk).exists())

    def test_owner_isolation_on_every_analysis_action(self):
        pk = self.create_analysis()["id"]
        self.authenticate(self.other)
        self.assertEqual(self.client.get(ROOT + "analyses/").data["count"], 0)
        for method, path, payload in [
            ("get", "", None), ("patch", "", {"price": "1"}), ("delete", "", None),
            ("post", "decision/", {"decision": "buy"}), ("post", "refresh-carbon/", {}),
        ]:
            with self.subTest(method=method, path=path):
                response = getattr(self.client, method)(f"{ROOT}analyses/{pk}/{path}", payload, format="json")
                self.assertEqual(response.status_code, 404)

    def test_validation_and_malformed_json(self):
        for fields in [
            {"price": "NaN"}, {"price": "0"}, {"budget": "-1"},
            {"expected_wears": 2147483648}, {"expected_wears": 1.5},
            {"material": "cotton", "weight_kg": None}, {"material": "", "weight_kg": "0.5"},
            {"product_url": "javascript:alert(1)"}, {"category": "invalid"},
        ]:
            with self.subTest(fields=fields):
                response = self.client.post(ROOT + "analyses/", {**DATA, **fields}, format="json")
                self.assertEqual(response.status_code, 400, response.data)
        response = self.client.post(ROOT + "analyses/", '{"bad":', content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(PurchaseAnalysis.objects.count(), 0)

    def test_decision_reset_only_on_changed_inputs_and_patch_cross_validation(self):
        pk = self.create_analysis()["id"]
        url = f"{ROOT}analyses/{pk}/"
        self.assertEqual(self.client.post(url + "decision/", {}, format="json").status_code, 400)
        self.assertEqual(self.client.post(url + "decision/", {"decision": "buy"}, format="json").status_code, 200)
        response = self.client.patch(url, {"price": "300000"}, format="json")
        self.assertEqual(response.data["decision"], "buy")
        response = self.client.patch(url, {"price": "400000"}, format="json")
        self.assertEqual(response.data["decision"], "undecided")
        self.assertIsNone(response.data["decided_at"])
        self.assertEqual(self.client.patch(url, {"material": "cotton"}, format="json").status_code, 400)

    @patch("worth_to_buy_analyzer.services.compute_co2e", side_effect=ValueError("offline"))
    def test_carbon_failure_does_not_block_create_or_refresh(self, compute):
        created = self.create_analysis(material="cotton", weight_kg="0.50")
        self.assertIsNone(created["carbon_kg_co2e"])
        self.assertTrue(created["notice"])
        response = self.client.post(f'{ROOT}analyses/{created["id"]}/refresh-carbon/')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["notice"])

    def test_analyzer_reference_crud_publication_and_catalogue_visibility(self):
        self.assertEqual(self.client.get(ROOT + "references/").status_code, 403)
        self.authenticate(self.analyzer)
        self.assertEqual(self.client.get(ROOT + "analyses/").status_code, 403)
        self.assertEqual(self.client.get(ROOT + "catalogue/").status_code, 403)
        response = self.client.post(ROOT + "references/", self.reference_data(), format="json")
        self.assertEqual(response.status_code, 201, response.data)
        pk = response.data["id"]
        url = f"{ROOT}references/{pk}/"
        self.assertEqual(response.data["created_by"], self.analyzer.pk)
        self.authenticate(self.user)
        self.assertEqual(self.client.get(ROOT + "catalogue/").data["count"], 0)
        self.assertEqual(self.client.get(f"{ROOT}catalogue/{pk}/").status_code, 404)
        self.authenticate(self.analyzer)
        self.assertEqual(self.client.post(url + "publication/", {}, format="json").status_code, 400)
        for _ in range(2):
            response = self.client.post(url + "publication/", {"is_published": True}, format="json")
            self.assertTrue(response.data["is_published"])
        self.assertEqual(self.client.patch(url, {"notes": "Diperbarui"}, format="json").status_code, 200)
        self.authenticate(self.user)
        response = self.client.get(ROOT + "catalogue/?q=Kemeja&category=top")
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(self.client.post(ROOT + "catalogue/", self.reference_data(), format="json").status_code, 405)
        self.assertEqual(self.client.get(ROOT + "catalogue/?category=invalid").status_code, 400)
        saved = self.create_analysis()["id"]
        self.authenticate(self.analyzer)
        self.assertEqual(self.client.delete(url).status_code, 204)
        self.assertTrue(PurchaseAnalysis.objects.filter(pk=saved).exists())

    def test_pagination_options_and_superuser_can_access_both_roles(self):
        self.authenticate(self.admin)
        for index in range(13):
            ClothingReference.objects.create(**self.reference_data(clothing_name=f"Pakaian {index}", is_published=True))
        response = self.client.get(ROOT + "catalogue/")
        self.assertEqual(response.data["count"], 13)
        self.assertEqual(len(response.data["results"]), 12)
        self.assertIsNotNone(response.data["next"])
        self.assertEqual(len(self.client.get(ROOT + "catalogue/?page=2").data["results"]), 1)
        self.assertEqual(self.client.get(ROOT + "references/").status_code, 200)
        options = self.client.get(ROOT + "options/").data
        self.assertIn({"value": "top", "label": "Atasan"}, options["categories"])
        self.assertIn({"value": "buy", "label": "Beli dengan rencana pemakaian"}, options["decisions"])
