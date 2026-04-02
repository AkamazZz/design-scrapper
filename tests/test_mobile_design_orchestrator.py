from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "skills" / "design-scraper" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from mobile_design_orchestrator.config_loader import load_orchestrator_config  # noqa: E402
from mobile_design_orchestrator.pipeline import (  # noqa: E402
    PROPOSAL_ARCHETYPES,
    SCREEN_STRUCTURE_PROFILES,
    SIGNAL_CLUSTER_DEFINITIONS,
    run_pipeline,
)
from mobile_design_orchestrator.project import (  # noqa: E402
    CHROME_DENSITY_BY_CONTRACT_DENSITY,
    CTA_POSTURE_BY_BUTTON_VARIANT,
    SCREEN_EFFECT_PROFILES,
    append_idea,
    validate_output_dir,
)


class MobileDesignOrchestratorTest(unittest.TestCase):
    def test_externalized_policy_config_is_loaded(self) -> None:
        config = load_orchestrator_config()

        self.assertEqual(config["config_version"], "1.0.0")
        self.assertEqual(PROPOSAL_ARCHETYPES, config["proposal_archetypes"])
        self.assertEqual(SIGNAL_CLUSTER_DEFINITIONS, config["signal_clusters"])
        self.assertEqual(SCREEN_STRUCTURE_PROFILES, config["screen_structure_profiles"])
        self.assertEqual(SCREEN_EFFECT_PROFILES, config["screen_effect_profiles"])
        self.assertEqual(
            CTA_POSTURE_BY_BUTTON_VARIANT["pill_single_cta"],
            set(config["validation_policies"]["cta_posture_by_button_variant"]["pill_single_cta"]),
        )
        self.assertEqual(
            CHROME_DENSITY_BY_CONTRACT_DENSITY["airy"],
            set(config["validation_policies"]["chrome_density_by_contract_density"]["airy"]),
        )

    def _run_workspace(
        self,
        output_dir: Path,
        project_name: str,
        title: str,
        summary: str,
        rationale: str,
        pattern_category: str,
        target_screens: list[str],
    ) -> tuple[dict[str, object], Path]:
        scrape_root = REPO_ROOT / "design_scrapped" / "initial"
        self.assertTrue((scrape_root / "metadata" / "index.json").exists())
        ingest_report = run_pipeline(
            output_dir=output_dir,
            project_name=project_name,
            platforms=["flutter", "swiftui", "compose"],
            phases=["ingest", "ideas"],
            scrape_root=scrape_root,
            force=True,
        )
        self.assertEqual(ingest_report["status"], "completed")

        append_idea(
            output_dir=output_dir,
            title=title,
            summary=summary,
            rationale=rationale,
            pattern_category=pattern_category,
            source_urls=[
                "https://mobbin.com/apps/headspace-ios-28986bf8-81b2-4af0-84df-b5654a8c98f9/f2c7edab-00b5-460c-9663-1cf64517f7db/screens"
            ],
            source_assets=[],
            target_screens=target_screens,
            status="candidate",
        )

        report = run_pipeline(
            output_dir=output_dir,
            project_name=project_name,
            platforms=["flutter", "swiftui", "compose"],
            phases=["proposal", "contract", "screens", "platforms", "plan", "validate"],
            force=True,
        )

        self.assertEqual(report["status"], "completed")
        self.assertEqual(report["validation_status"], "passed")
        return report, output_dir

    def _read_json(self, output_dir: Path, relative_path: str) -> dict[str, object]:
        return json.loads((output_dir / relative_path).read_text())

    def _screen_by_id(self, screens: dict[str, object], screen_id: str) -> dict[str, object]:
        for screen in screens.get("screens", []):
            if screen.get("screen_id") == screen_id:
                return screen
        self.fail(f"Missing screen {screen_id}")

    def test_full_handoff_flow_from_sample_scrape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            _, output_dir = self._run_workspace(
                output_dir=Path(tmp_dir) / "workspace",
                project_name="Headspace Mobile",
                title="Calm single-action onboarding",
                summary="Use one dominant CTA and progressive disclosure in onboarding.",
                rationale="The reference set consistently reduces competing actions in early flows.",
                pattern_category="onboarding",
                target_screens=["onboarding"],
            )

            inspirations = self._read_json(output_dir, "inspirations/index.json")
            design_signals = self._read_json(output_dir, "proposal/design_signals.json")
            direction_options = self._read_json(output_dir, "proposal/direction_options.json")
            proposal_candidates = self._read_json(output_dir, "proposal/proposal_candidates.json")
            review_packet = (output_dir / "proposal" / "review_packet.md").read_text()
            visual_language = self._read_json(output_dir, "proposal/visual_language.json")
            typography_voice = self._read_json(output_dir, "proposal/typography_voice.json")
            source_rationale = self._read_json(output_dir, "proposal/source_rationale.json")
            tokens = self._read_json(output_dir, "contract/tokens.json")
            contract_typography = self._read_json(output_dir, "contract/typography.json")
            semantics = self._read_json(output_dir, "contract/semantics.json")
            screens = self._read_json(output_dir, "screens/index.json")
            flutter_guidance = self._read_json(output_dir, "platforms/flutter.json")
            plan = self._read_json(output_dir, "realization/plan.json")
            validation = self._read_json(output_dir, "validation/report.json")
            brief = self._read_json(output_dir, "contract/brief.json")
            onboarding = self._screen_by_id(screens, "onboarding")

            self.assertEqual(inspirations["summary"]["asset_count"], 24)
            self.assertEqual(design_signals["source_patterns"]["source_count"], 2)
            self.assertEqual(design_signals["idea_patterns"]["idea_count"], 1)
            self.assertEqual(design_signals["screen_pressure"]["primary_screen"], "onboarding")
            self.assertEqual(design_signals["signal_clusters"]["dominant_cluster_id"], "onboarding_editorial")
            self.assertIn("onboarding_editorial", design_signals["signal_clusters"]["active_cluster_ids"])
            self.assertGreaterEqual(design_signals["signal_clusters"]["active_cluster_count"], 1)
            self.assertEqual(design_signals["archetype_scores"][0]["direction_id"], visual_language["direction_id"])
            self.assertGreater(design_signals["archetype_scores"][0]["cluster_score"], 0)
            self.assertTrue(
                any(match["cluster_id"] == "onboarding_editorial" for match in design_signals["archetype_scores"][0]["cluster_matches"])
            )
            self.assertEqual(direction_options["selected_direction_id"], visual_language["direction_id"])
            self.assertGreaterEqual(len(direction_options["options"]), 1)
            self.assertEqual(direction_options["options"][0]["rank"], 1)
            self.assertTrue(direction_options["options"][0]["selected"])
            self.assertEqual(direction_options["options"][0]["direction_id"], visual_language["direction_id"])
            self.assertEqual(direction_options["options"][0]["evidence"]["dominant_cluster_id"], "onboarding_editorial")
            self.assertEqual(proposal_candidates["selected_direction_id"], visual_language["direction_id"])
            self.assertEqual(proposal_candidates["candidate_count"], 3)
            self.assertEqual(len(proposal_candidates["candidates"]), 3)
            self.assertEqual(proposal_candidates["candidates"][0]["direction_id"], visual_language["direction_id"])
            self.assertTrue(proposal_candidates["candidates"][0]["selected"])
            self.assertTrue(proposal_candidates["candidates"][0]["selection_rationale"])
            self.assertTrue(proposal_candidates["candidates"][1]["rejection_rationale"])
            self.assertGreaterEqual(len(proposal_candidates["non_negotiables"]), 2)
            self.assertGreaterEqual(len(proposal_candidates["open_questions"]), 2)
            self.assertIn("## Selected Direction", review_packet)
            self.assertIn("## Candidate Review", review_packet)
            for candidate in proposal_candidates["candidates"]:
                self.assertIn(candidate["direction_name"], review_packet)
            self.assertEqual(visual_language["direction_id"], "calm_editorial")
            self.assertEqual(typography_voice["direction_id"], visual_language["direction_id"])
            self.assertEqual(source_rationale["idea_coverage"]["covered_idea_count"], 1)
            self.assertEqual(source_rationale["source_coverage"]["covered_source_count"], 2)
            self.assertGreaterEqual(len(screens["screens"]), 1)
            self.assertEqual(screens["screens"][0]["components"][0]["semantic_role"], "app.title")
            self.assertEqual(tokens["proposal_context"]["density_profile"], "airy")
            self.assertEqual(tokens["proposal_context"]["spacing_rhythm"], "breathing_room")
            self.assertEqual(tokens["spacing"]["40"]["value"], 40)
            self.assertEqual(tokens["radius"]["lg"]["value"], 24)
            self.assertEqual(tokens["motion"]["duration.slow"]["value"], 320)
            self.assertEqual(tokens["motion"]["scale.pressed"]["value"], 0.99)
            self.assertEqual(contract_typography["defaults"]["paragraph_spacing"], 4)
            self.assertEqual(semantics["spacing_roles"]["section.gap"], "spacing.28")
            self.assertEqual(semantics["shape_roles"]["hero.corner"], "radius.lg")
            self.assertEqual(semantics["state_roles"]["pressed.scale"], "motion.scale.pressed")
            self.assertEqual(semantics["component_roles"]["button.primary"]["variant"], "pill_single_cta")
            self.assertEqual(semantics["component_roles"]["card.default"]["surface_style"], "matte_layers")
            self.assertEqual(onboarding["layout_strategy"], "hero_stack")
            self.assertEqual(onboarding["cta_posture"], "footer_single")
            self.assertEqual(onboarding["chrome_density"], "low")
            self.assertEqual(onboarding["card_usage"], "single_soft_anchor")
            self.assertEqual(onboarding["motif_application"]["primary_motif"], "hero_breathing_card")
            self.assertEqual(onboarding["components"][-1]["semantic_role"], "button.primary")
            self.assertIn("progress", [component["kind"] for component in onboarding["components"]])
            self.assertEqual(brief["proposal_context"]["direction_id"], visual_language["direction_id"])
            self.assertEqual(brief["proposal_context"]["density_profile"], "airy")
            self.assertEqual(brief["technical_constraints"]["density_profile"], "airy")
            self.assertEqual(brief["technical_constraints"]["primary_action_posture"], "pill_single_cta")
            self.assertEqual(screens["proposal_context"]["direction_id"], visual_language["direction_id"])
            self.assertEqual(screens["proposal_context"]["screen_structure_phase"], "phase_4_screen_structure")
            self.assertIn("design_intent", flutter_guidance)
            self.assertIn("typography_guidance", flutter_guidance)
            self.assertIn("visual_guidance", flutter_guidance)
            self.assertNotIn("token_mapping", flutter_guidance)
            self.assertEqual(plan["status"], "ready_for_implementation")
            self.assertEqual(validation["status"], "passed")
            self.assertEqual(brief["inspiration_context"]["asset_count"], 24)

    def test_screen_structure_changes_with_selected_proposal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            _, calm_output = self._run_workspace(
                output_dir=Path(tmp_dir) / "calm",
                project_name="Headspace Mobile",
                title="Calm single-action onboarding",
                summary="Use one dominant CTA and progressive disclosure in onboarding.",
                rationale="The reference set consistently reduces competing actions in early flows.",
                pattern_category="onboarding",
                target_screens=["onboarding"],
            )
            _, utility_output = self._run_workspace(
                output_dir=Path(tmp_dir) / "utility",
                project_name="Cash Wallet Dashboard",
                title="Fast account dashboard",
                summary="Lead with the main balance, action strip, and segmented modules for payments.",
                rationale="Cash flows need a metric-first home, fast review paths, and dense but ordered support modules.",
                pattern_category="dashboard",
                target_screens=["home", "detail"],
            )

            calm_visual = self._read_json(calm_output, "proposal/visual_language.json")
            utility_visual = self._read_json(utility_output, "proposal/visual_language.json")
            calm_screens = self._read_json(calm_output, "screens/index.json")
            utility_screens = self._read_json(utility_output, "screens/index.json")

            self.assertEqual(calm_visual["direction_id"], "calm_editorial")
            self.assertEqual(utility_visual["direction_id"], "utility_bold")

            calm_onboarding = self._screen_by_id(calm_screens, "onboarding")
            utility_home = self._screen_by_id(utility_screens, "home")

            self.assertEqual(calm_onboarding["layout_strategy"], "hero_stack")
            self.assertEqual(calm_onboarding["cta_posture"], "footer_single")
            self.assertEqual(calm_onboarding["chrome_density"], "low")
            self.assertEqual(calm_onboarding["card_usage"], "single_soft_anchor")
            self.assertEqual(calm_onboarding["components"][-1]["semantic_role"], "button.primary")
            self.assertIn("progress", [component["kind"] for component in calm_onboarding["components"]])

            self.assertEqual(utility_home["layout_strategy"], "metric_first_dashboard")
            self.assertEqual(utility_home["cta_posture"], "inline_action_strip")
            self.assertEqual(utility_home["chrome_density"], "high")
            self.assertEqual(utility_home["card_usage"], "segmented_modules")
            self.assertEqual(utility_home["motif_application"]["primary_motif"], "metric_stack")
            utility_component_kinds = [component["kind"] for component in utility_home["components"]]
            self.assertIn("list", utility_component_kinds)
            self.assertIn("chip", utility_component_kinds)
            primary_button_index = next(
                index
                for index, component in enumerate(utility_home["components"])
                if component.get("semantic_role") == "button.primary"
            )
            first_support_index = next(
                index
                for index, component in enumerate(utility_home["components"])
                if component.get("kind") in {"list", "divider"}
            )
            self.assertLess(primary_button_index, first_support_index)
            self.assertNotEqual(calm_onboarding["layout_strategy"], utility_home["layout_strategy"])
            self.assertNotEqual(calm_onboarding["cta_posture"], utility_home["cta_posture"])
            self.assertNotEqual(calm_onboarding["chrome_density"], utility_home["chrome_density"])

    def test_playful_direction_builds_reward_oriented_screens(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            _, output_dir = self._run_workspace(
                output_dir=Path(tmp_dir) / "playful",
                project_name="Habitica Streak Challenge",
                title="Reward-driven lesson streak board",
                summary="Lead with reward badges, visible streak progress, and challenge cards for the next lesson.",
                rationale="Game-like momentum needs modular wins, visible rewards, and short upbeat follow-up actions.",
                pattern_category="progress",
                target_screens=["home", "progress", "detail"],
            )

            visual_language = self._read_json(output_dir, "proposal/visual_language.json")
            design_signals = self._read_json(output_dir, "proposal/design_signals.json")
            direction_options = self._read_json(output_dir, "proposal/direction_options.json")
            screens = self._read_json(output_dir, "screens/index.json")
            home = self._screen_by_id(screens, "home")
            progress = self._screen_by_id(screens, "progress")

            self.assertEqual(visual_language["direction_id"], "playful_modular")
            self.assertEqual(design_signals["signal_clusters"]["dominant_cluster_id"], "reward_progress")
            self.assertIn("reward_progress", design_signals["signal_clusters"]["active_cluster_ids"])
            self.assertGreater(design_signals["archetype_scores"][0]["cluster_score"], 0)
            self.assertTrue(
                any(match["cluster_id"] == "reward_progress" for match in design_signals["archetype_scores"][0]["cluster_matches"])
            )
            self.assertEqual(direction_options["selected_direction_id"], "playful_modular")
            self.assertEqual(
                [entry["rank"] for entry in direction_options["options"]],
                list(range(1, len(direction_options["options"]) + 1)),
            )
            self.assertEqual(direction_options["options"][0]["direction_id"], "playful_modular")
            self.assertTrue(direction_options["options"][0]["selected"])
            self.assertEqual(direction_options["options"][0]["evidence"]["dominant_cluster_id"], "reward_progress")
            self.assertIn("reward_progress", direction_options["options"][0]["evidence"]["supporting_clusters"])

            self.assertEqual(home["layout_strategy"], "modular_reward_home")
            self.assertEqual(home["cta_posture"], "progressive_reward")
            self.assertEqual(home["chrome_density"], "medium")
            self.assertEqual(home["card_usage"], "stacked_reward_modules")
            self.assertEqual(home["motif_application"]["primary_motif"], "reward_badge_row")
            home_component_kinds = [component["kind"] for component in home["components"]]
            self.assertIn("badge", home_component_kinds)
            self.assertIn("progress", home_component_kinds)
            self.assertIn("card", home_component_kinds)
            self.assertIn("button", home_component_kinds)

            self.assertEqual(progress["layout_strategy"], "momentum_board")
            self.assertEqual(progress["cta_posture"], "progressive_reward")
            self.assertEqual(progress["motif_application"]["primary_motif"], "reward_badge_row")
            progress_component_kinds = [component["kind"] for component in progress["components"]]
            self.assertIn("badge", progress_component_kinds)
            self.assertIn("progress", progress_component_kinds)
            self.assertIn("button", progress_component_kinds)

    def test_validation_fails_for_generic_stale_screens_with_aligned_direction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            _, output_dir = self._run_workspace(
                output_dir=Path(tmp_dir) / "workspace",
                project_name="Headspace Mobile",
                title="Calm single-action onboarding",
                summary="Use one dominant CTA and progressive disclosure in onboarding.",
                rationale="The reference set consistently reduces competing actions in early flows.",
                pattern_category="onboarding",
                target_screens=["onboarding"],
            )

            screens = self._read_json(output_dir, "screens/index.json")
            onboarding = self._screen_by_id(screens, "onboarding")
            onboarding["components"] = [
                {
                    "id": "onboarding_title",
                    "kind": "text",
                    "semantic_role": "app.display",
                    "content": "Calm single-action onboarding",
                },
                {
                    "id": "onboarding_body",
                    "kind": "text",
                    "semantic_role": "app.body",
                    "content": "Use one dominant CTA and progressive disclosure in onboarding.",
                },
                {
                    "id": "onboarding_card",
                    "kind": "card",
                    "semantic_role": "card.default",
                    "content": "Hero Breathing Card",
                },
                {
                    "id": "onboarding_primary",
                    "kind": "button",
                    "semantic_role": "button.primary",
                    "label": "Continue",
                },
            ]
            onboarding["motif_application"] = {
                "primary_motif": "hero_breathing_card",
                "secondary_motifs": [],
                "placement": [
                    {
                        "component_id": "onboarding_card",
                        "motif_id": "hero_breathing_card",
                        "purpose": "anchor surface",
                    }
                ],
            }
            (output_dir / "screens" / "index.json").write_text(json.dumps(screens, indent=2, sort_keys=True) + "\n")

            validation = validate_output_dir(output_dir, required_platforms=["flutter", "swiftui", "compose"])

            self.assertEqual(validation["status"], "failed")
            error_codes = {error["code"] for error in validation["errors"]}
            self.assertIn("screen_structure_stale", error_codes)

    def test_validation_fails_for_missing_signal_clusters(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            _, output_dir = self._run_workspace(
                output_dir=Path(tmp_dir) / "workspace",
                project_name="Headspace Mobile",
                title="Calm single-action onboarding",
                summary="Use one dominant CTA and progressive disclosure in onboarding.",
                rationale="The reference set consistently reduces competing actions in early flows.",
                pattern_category="onboarding",
                target_screens=["onboarding"],
            )

            design_signals = self._read_json(output_dir, "proposal/design_signals.json")
            design_signals["signal_clusters"] = {}
            (output_dir / "proposal" / "design_signals.json").write_text(
                json.dumps(design_signals, indent=2, sort_keys=True) + "\n"
            )

            validation = validate_output_dir(output_dir, required_platforms=["flutter", "swiftui", "compose"])

            self.assertEqual(validation["status"], "failed")
            self.assertIn(
                "proposal_incomplete",
                {error["code"] for error in validation["errors"]},
            )
            self.assertTrue(
                any("clustered signal evidence" in error["message"] for error in validation["errors"]),
                validation["errors"],
            )

    def test_contract_phase_fails_cleanly_without_proposal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir) / "workspace"
            scrape_root = REPO_ROOT / "design_scrapped" / "initial"

            ingest_report = run_pipeline(
                output_dir=output_dir,
                project_name="Headspace Mobile",
                platforms=["flutter", "swiftui", "compose"],
                phases=["ingest", "ideas"],
                scrape_root=scrape_root,
                force=True,
            )
            self.assertEqual(ingest_report["status"], "completed")

            report = run_pipeline(
                output_dir=output_dir,
                project_name="Headspace Mobile",
                platforms=["flutter", "swiftui", "compose"],
                phases=["contract"],
                force=True,
            )

            self.assertEqual(report["status"], "failed")
            self.assertEqual(report["validation_status"], "failed")
            validation = self._read_json(output_dir, "validation/report.json")
            self.assertEqual(validation["status"], "failed")
            self.assertEqual(validation["errors"][0]["code"], "proposal_missing")

    def test_validation_fails_for_direction_option_ordering_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            _, output_dir = self._run_workspace(
                output_dir=Path(tmp_dir) / "workspace",
                project_name="Headspace Mobile",
                title="Calm single-action onboarding",
                summary="Use one dominant CTA and progressive disclosure in onboarding.",
                rationale="The reference set consistently reduces competing actions in early flows.",
                pattern_category="onboarding",
                target_screens=["onboarding"],
            )

            direction_options = self._read_json(output_dir, "proposal/direction_options.json")
            self.assertGreaterEqual(len(direction_options["options"]), 2)
            direction_options["options"][0]["rank"] = 2
            direction_options["options"][1]["rank"] = 1
            (output_dir / "proposal" / "direction_options.json").write_text(
                json.dumps(direction_options, indent=2, sort_keys=True) + "\n"
            )

            validation = validate_output_dir(output_dir, required_platforms=["flutter", "swiftui", "compose"])

            self.assertEqual(validation["status"], "failed")
            mismatch_messages = [
                error["message"]
                for error in validation["errors"]
                if error["code"] == "proposal_mismatch"
            ]
            self.assertTrue(mismatch_messages)
            self.assertTrue(
                any("deterministic score ordering" in message for message in mismatch_messages),
                mismatch_messages,
            )

    def test_validation_fails_for_selected_candidate_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            _, output_dir = self._run_workspace(
                output_dir=Path(tmp_dir) / "workspace",
                project_name="Headspace Mobile",
                title="Calm single-action onboarding",
                summary="Use one dominant CTA and progressive disclosure in onboarding.",
                rationale="The reference set consistently reduces competing actions in early flows.",
                pattern_category="onboarding",
                target_screens=["onboarding"],
            )

            proposal_candidates = self._read_json(output_dir, "proposal/proposal_candidates.json")
            proposal_candidates["selected_direction_id"] = "utility_bold"
            (output_dir / "proposal" / "proposal_candidates.json").write_text(
                json.dumps(proposal_candidates, indent=2, sort_keys=True) + "\n"
            )

            validation = validate_output_dir(output_dir, required_platforms=["flutter", "swiftui", "compose"])

            self.assertEqual(validation["status"], "failed")
            mismatch_messages = [
                error["message"]
                for error in validation["errors"]
                if error["code"] == "proposal_mismatch"
            ]
            self.assertTrue(mismatch_messages)
            self.assertTrue(
                any("selected_direction_id does not match the selected proposal direction" in message for message in mismatch_messages),
                mismatch_messages,
            )


if __name__ == "__main__":
    unittest.main()
