"""
Regression tests for Make.com blueprint templates.

These tests ensure blueprint templates remain structurally valid and
deployment-ready. Breaking changes here will cause deployment failures.
"""

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.regression


class TestBlueprintTemplateExistence:
    """Ensure all required blueprint templates exist."""

    def test_all_capability_blueprints_exist(self) -> None:
        """All supported capabilities must have blueprint templates."""
        capabilities = ["availability", "booking", "cancellation", "rescheduling"]
        blueprint_dir = Path("ground-truth/configs/make_blueprints")

        for capability in capabilities:
            blueprint_path = blueprint_dir / f"{capability}.json"
            assert blueprint_path.exists(), (
                f"Missing blueprint template for capability: {capability}. "
                f"Expected at {blueprint_path}"
            )


class TestBlueprintStructuralValidity:
    """Test blueprint templates have valid JSON structure and required fields."""

    @pytest.mark.parametrize(
        "capability",
        ["availability", "booking", "cancellation", "rescheduling"],
    )
    def test_blueprint_is_valid_json(self, capability: str) -> None:
        """Blueprint must be valid JSON."""
        blueprint_path = Path(f"ground-truth/configs/make_blueprints/{capability}.json")

        try:
            with open(blueprint_path, encoding="utf-8") as f:
                blueprint = json.load(f)
        except json.JSONDecodeError as e:
            pytest.fail(f"Blueprint {capability}.json is not valid JSON: {e}")

        assert isinstance(blueprint, dict), f"Blueprint {capability}.json is not a JSON object"

    @pytest.mark.parametrize(
        "capability",
        ["availability", "booking", "cancellation", "rescheduling"],
    )
    def test_blueprint_has_required_fields(self, capability: str) -> None:
        """Blueprint must have required top-level fields."""
        blueprint_path = Path(f"ground-truth/configs/make_blueprints/{capability}.json")

        with open(blueprint_path, encoding="utf-8") as f:
            blueprint = json.load(f)

        required_fields = ["name", "flow", "metadata"]
        for field in required_fields:
            assert field in blueprint, (
                f"Blueprint {capability}.json missing required field: {field}. "
                f"This will cause deployment failures."
            )

    @pytest.mark.parametrize(
        "capability",
        ["availability", "booking", "cancellation", "rescheduling"],
    )
    def test_blueprint_flow_is_list(self, capability: str) -> None:
        """Blueprint flow must be a list of modules."""
        blueprint_path = Path(f"ground-truth/configs/make_blueprints/{capability}.json")

        with open(blueprint_path, encoding="utf-8") as f:
            blueprint = json.load(f)

        assert isinstance(blueprint["flow"], list), (
            f"Blueprint {capability}.json flow must be a list, got {type(blueprint['flow'])}"
        )

    @pytest.mark.parametrize(
        "capability",
        ["availability", "booking", "cancellation", "rescheduling"],
    )
    def test_blueprint_flow_not_empty(self, capability: str) -> None:
        """Blueprint flow must contain at least one module."""
        blueprint_path = Path(f"ground-truth/configs/make_blueprints/{capability}.json")

        with open(blueprint_path, encoding="utf-8") as f:
            blueprint = json.load(f)

        assert len(blueprint["flow"]) > 0, (
            f"Blueprint {capability}.json has empty flow. Must contain at least webhook module."
        )


class TestBlueprintModuleStructure:
    """Test module structure within blueprints."""

    @pytest.mark.parametrize(
        "capability",
        ["availability", "booking", "cancellation", "rescheduling"],
    )
    def test_all_modules_have_required_fields(self, capability: str) -> None:
        """Each module must have id, module, version, and mapper fields."""
        blueprint_path = Path(f"ground-truth/configs/make_blueprints/{capability}.json")

        with open(blueprint_path, encoding="utf-8") as f:
            blueprint = json.load(f)

        required_module_fields = ["id", "module", "version", "mapper"]

        for idx, module in enumerate(blueprint["flow"]):
            for field in required_module_fields:
                assert field in module, (
                    f"Blueprint {capability}.json module {idx} missing required field: {field}"
                )

    @pytest.mark.parametrize(
        "capability",
        ["availability", "booking", "cancellation", "rescheduling"],
    )
    def test_first_module_is_webhook(self, capability: str) -> None:
        """First module must be a webhook trigger."""
        blueprint_path = Path(f"ground-truth/configs/make_blueprints/{capability}.json")

        with open(blueprint_path, encoding="utf-8") as f:
            blueprint = json.load(f)

        first_module = blueprint["flow"][0]
        module_name = first_module.get("module", "")

        # Must be one of the valid webhook module variants
        valid_webhook_names = ["gateway:CustomWebHook", "webhook:CustomWebHook"]

        assert module_name in valid_webhook_names, (
            f"Blueprint {capability}.json first module must be webhook trigger. "
            f"Got: {module_name}, expected one of: {valid_webhook_names}"
        )


class TestBlueprintModuleCountRegression:
    """
    REGRESSION: Module counts must match actual baseline.

    These counts establish the stable baseline. Changes require verification
    that the new blueprint structure is intentional and correct.
    """

    def test_availability_has_4_modules(self) -> None:
        """Availability blueprint must have exactly 4 modules."""
        blueprint_path = Path("ground-truth/configs/make_blueprints/availability.json")

        with open(blueprint_path, encoding="utf-8") as f:
            blueprint = json.load(f)

        assert len(blueprint["flow"]) == 4, (
            f"Availability blueprint module count changed. "
            f"Expected 4, got {len(blueprint['flow'])}. "
            f"Verify this change is intentional."
        )

    def test_booking_has_5_modules(self) -> None:
        """Booking blueprint must have exactly 5 modules."""
        blueprint_path = Path("ground-truth/configs/make_blueprints/booking.json")

        with open(blueprint_path, encoding="utf-8") as f:
            blueprint = json.load(f)

        assert len(blueprint["flow"]) == 5, (
            f"Booking blueprint module count changed. "
            f"Expected 5, got {len(blueprint['flow'])}. "
            f"Verify this change is intentional."
        )

    def test_cancellation_has_4_modules(self) -> None:
        """Cancellation blueprint must have exactly 4 modules."""
        blueprint_path = Path("ground-truth/configs/make_blueprints/cancellation.json")

        with open(blueprint_path, encoding="utf-8") as f:
            blueprint = json.load(f)

        assert len(blueprint["flow"]) == 4, (
            f"Cancellation blueprint module count changed. "
            f"Expected 4, got {len(blueprint['flow'])}. "
            f"Verify this change is intentional."
        )

    def test_rescheduling_has_5_modules(self) -> None:
        """Rescheduling blueprint must have exactly 5 modules."""
        blueprint_path = Path("ground-truth/configs/make_blueprints/rescheduling.json")

        with open(blueprint_path, encoding="utf-8") as f:
            blueprint = json.load(f)

        assert len(blueprint["flow"]) == 5, (
            f"Rescheduling blueprint module count changed. "
            f"Expected 5, got {len(blueprint['flow'])}. "
            f"Verify this change is intentional."
        )


class TestBlueprintParameterizationRegression:
    """
    REGRESSION: Blueprints must contain placeholder patterns for parameterization.

    The orchestrator injects real hook IDs and connection IDs before deployment.
    Missing placeholders will cause injection failures.
    """

    @pytest.mark.parametrize(
        "capability",
        ["availability", "booking", "cancellation", "rescheduling"],
    )
    def test_blueprint_contains_hook_placeholder_or_url(self, capability: str) -> None:
        """
        Blueprint must contain webhook configuration.

        Either as a placeholder pattern or a URL field that can be injected.
        """
        blueprint_path = Path(f"ground-truth/configs/make_blueprints/{capability}.json")

        with open(blueprint_path, encoding="utf-8") as f:
            blueprint = json.load(f)

        # Convert to string to search for patterns
        blueprint_str = json.dumps(blueprint)

        # Check for webhook configuration patterns
        has_webhook_config = (
            "webhook" in blueprint_str.lower()
            or "hook" in blueprint_str.lower()
            or "url" in blueprint_str.lower()
        )

        assert has_webhook_config, (
            f"Blueprint {capability}.json appears to be missing webhook configuration. "
            f"This will prevent hook_id injection during deployment."
        )


class TestBlueprintMetadataRegression:
    """
    REGRESSION: Blueprint metadata must remain stable.

    Metadata affects scenario identification and tracking.
    """

    @pytest.mark.parametrize(
        "capability",
        ["availability", "booking", "cancellation", "rescheduling"],
    )
    def test_blueprint_has_metadata_section(self, capability: str) -> None:
        """Blueprint must contain metadata section."""
        blueprint_path = Path(f"ground-truth/configs/make_blueprints/{capability}.json")

        with open(blueprint_path, encoding="utf-8") as f:
            blueprint = json.load(f)

        assert "metadata" in blueprint, f"Blueprint {capability}.json missing metadata section"

        metadata = blueprint["metadata"]

        # Metadata should contain identifying information
        expected_fields = ["version", "capability", "template_version"]

        for field in expected_fields:
            assert field in metadata, f"Blueprint {capability}.json metadata missing field: {field}"

    @pytest.mark.parametrize(
        "capability",
        ["availability", "booking", "cancellation", "rescheduling"],
    )
    def test_blueprint_capability_matches_filename(self, capability: str) -> None:
        """Blueprint metadata capability must match filename."""
        blueprint_path = Path(f"ground-truth/configs/make_blueprints/{capability}.json")

        with open(blueprint_path, encoding="utf-8") as f:
            blueprint = json.load(f)

        metadata = blueprint.get("metadata", {})
        metadata_capability = metadata.get("capability", "")

        assert metadata_capability == capability, (
            f"Blueprint {capability}.json has mismatched capability in metadata: {metadata_capability}"
        )


class TestBlueprintNamingRegression:
    """
    REGRESSION: Blueprint naming must follow expected patterns.

    Names are used for identification in Make.com dashboard.
    """

    @pytest.mark.parametrize(
        "capability",
        ["availability", "booking", "cancellation", "rescheduling"],
    )
    def test_blueprint_has_name_field(self, capability: str) -> None:
        """Blueprint must have a name field."""
        blueprint_path = Path(f"ground-truth/configs/make_blueprints/{capability}.json")

        with open(blueprint_path, encoding="utf-8") as f:
            blueprint = json.load(f)

        assert "name" in blueprint, (
            f"Blueprint {capability}.json missing name field. "
            f"This is required for scenario identification."
        )

        name = blueprint["name"]
        assert isinstance(name, str), f"Blueprint {capability}.json name must be a string"
        assert len(name) > 0, f"Blueprint {capability}.json name cannot be empty"


class TestBlueprintRouterSchemaRegression:
    """
    REGRESSION: Router routes must use Make-native filter schema.

    Make's API rejects a ``condition`` property on route objects with
    SC400 "should NOT have additional properties, additionalProperty:
    'condition'". Filters belong on the first module inside a route's flow,
    and the fallback route is marked via ``parameters.else``.
    """

    @pytest.mark.parametrize(
        "capability",
        ["cancellation", "rescheduling"],
    )
    def test_no_condition_key_on_router_routes(self, capability: str) -> None:
        """Route objects must not carry a 'condition' key."""
        blueprint_path = Path(f"ground-truth/configs/make_blueprints/{capability}.json")

        with open(blueprint_path, encoding="utf-8") as f:
            blueprint = json.load(f)

        for module in blueprint["flow"]:
            for route in module.get("routes", []):
                assert "condition" not in route, (
                    f"Blueprint {capability}.json route must not contain 'condition'. "
                    f"Make rejects it with SC400. Use 'filter' on the first module "
                    f"of the route flow instead."
                )

    @pytest.mark.parametrize(
        "capability",
        ["cancellation", "rescheduling"],
    )
    def test_router_marks_else_route(self, capability: str) -> None:
        """Routers must mark the fallback route via parameters.else."""
        blueprint_path = Path(f"ground-truth/configs/make_blueprints/{capability}.json")

        with open(blueprint_path, encoding="utf-8") as f:
            blueprint = json.load(f)

        for module in blueprint["flow"]:
            if module.get("module") == "builtin:BasicRouter":
                assert "else" in (module.get("parameters") or {}), (
                    f"Blueprint {capability}.json router must set parameters.else "
                    f"to mark its fallback route."
                )

    @pytest.mark.parametrize(
        "capability",
        ["cancellation", "rescheduling"],
    )
    def test_route_filters_on_first_module(self, capability: str) -> None:
        """Route filters must live on the first module of non-else route flows."""
        blueprint_path = Path(f"ground-truth/configs/make_blueprints/{capability}.json")

        with open(blueprint_path, encoding="utf-8") as f:
            blueprint = json.load(f)

        for module in blueprint["flow"]:
            if module.get("module") != "builtin:BasicRouter":
                continue
            else_index = (module.get("parameters") or {}).get("else")
            for idx, route in enumerate(module.get("routes", [])):
                if idx == else_index:
                    continue
                first_module = route.get("flow", [{}])[0]
                assert "filter" in first_module, (
                    f"Blueprint {capability}.json route {idx} must define its filter "
                    f"on the first module of the route flow. The Make API rejects "
                    f"route-level condition/filter properties."
                )
