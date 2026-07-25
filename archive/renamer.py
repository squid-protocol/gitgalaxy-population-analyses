import sqlite3
from pathlib import Path
import sys

# --- CONFIGURATION ---
DB_PATH = Path("gitgalaxy_master.db")

# The exact mapping from your old database columns to the new Blueprint taxonomy
RENAME_MAP = {
    # --- CORE PHYSICS (Structure, Geometry, Memory, State) ---
    "hit_control_flow_branches": "core_branch",
    "hit_sequential_logic_declarations": "core_linear",
    "hit_function_parameters": "core_args",
    "hit_function_method_declarations": "core_func_start",
    "hit_class_entity_declarations": "core_class_start",
    "hit_defensive_programming_constructs": "core_safety",
    "hit_type_safety_bypasses": "core_safety_neg",
    "hit_high_risk_execution_commands": "core_danger",
    "hit_exposed_api_public_exports": "core_api",
    "hit_state_mutations_variable_reassignments": "core_flux",
    "hit_asynchronous_concurrent_execution": "core_concurrency",
    "hit_closures_and_anonymous_functions": "core_closures",
    "hit_global_state_dependencies": "core_globals",
    "hit_collection_iterators_comprehensions": "core_comprehensions",
    "hit_metaprogramming_and_reflection": "core_heat_triggers",
    "hit_module_dependencies_imports": "core_import",
    "hit_event_publishers_emitters": "core_events",
    "hit_pointer_arithmetic_and_addressing": "core_pointers",
    "hit_manual_memory_allocation": "core_memory_alloc",
    "hit_inline_assembly_blocks": "core_inline_asm",
    "hit_explicit_type_casts": "core_cast_hits",
    "hit_fatal_aborts_and_exceptions": "core_bailout_hits",
    "hit_thread_sleeps_and_blocking_waits": "core_halt_hits",
    "hit_bitwise_operations": "core_bitwise_hits",
    "hit_thread_synchronization_locks": "core_sync_locks",
    "hit_immutable_data_declarations": "core_freeze_hits",
    "hit_resource_deallocation_and_cleanup": "core_cleanup",
    "hit_private_encapsulated_scopes": "core_encapsulation",
    "hit_event_listeners_and_subscribers": "core_listeners",

    # --- DESIGN (Domain, Frameworks, Intent, Debt) ---
    "hit_i_o_and_network_boundaries": "design_io",
    "hit_ui_view_layer_components": "design_ui_framework",
    "hit_scientific_and_mathematical_operations": "design_scientific",
    "hit_server_side_rendering_contexts": "design_ssr_boundaries",
    "hit_dependency_injection_constructs": "design_dependency_injection",
    "hit_preprocessor_macros": "design_macros",
    "hit_decorators_and_annotations": "design_decorators",
    "hit_generic_type_abstractions": "design_generics",
    "hit_hardware_bridge": "design_hardware",
    "hit_cryptography": "design_crypto",
    "hit_ipc_rpc_bridges": "design_ipc",
    "hit_serialization_parsing": "design_serialization",
    "hit_regex_execution": "design_regex",
    "hit_time_date_logic": "design_time",
    "hit_auth_middleware": "design_auth",
    "hit_feature_flags": "design_feature_flags",
    
    # --- DEBT & HUMAN ELEMENTS ---
    "hit_structured_documentation_blocks": "design_doc",
    "hit_commented_out_code_dead_logic": "design_graveyard",
    "hit_commented_out_executable_logic": "design_graveyard_exec",
    "hit_unit_test_assertions": "design_test",
    "hit_bypassed_skipped_tests": "design_test_skip",
    "hit_planned_work_todos": "design_planned_debt",
    "hit_acknowledged_tech_debt_fixmes": "design_fragile_debt",
    "hit_structured_telemetry_and_logging": "design_telemetry",
    "hit_ad_hoc_print_debug_statements": "design_print_hits",
    "hit_authorship_metadata": "design_ownership",
    "hit_specification_traceability_tags": "design_spec_exposure",
    "hit_indentation_faction": "design_civil_war",
    "hit_structural_tab_indentations": "design_tabs",
    "hit_structural_space_indentations": "design_spaces",

    # --- THREATS (Isolated Anomalies) ---
    "hit_embedded_credentials_and_keys": "threat_private_info",
    "hit_dynamic_code_execution_eval_exec": "threat_eval_exec",
    "hit_high_entropy_obfuscated_logic": "threat_obfuscated",
    "hit_safety_and_constraint_bypasses": "threat_bypasses",
    "hit_external_network_and_i_o_hooks": "threat_network_hooks",
    "hit_global_environment_mutation": "threat_env_mutation",
    "hit_non_standard_steganographic_imports": "threat_stego_imports",
    "hit_non_standard_unicode_homoglyphs": "threat_homoglyphs",
    "hit_low_level_bitwise_cryptographic_math": "threat_crypto_math",
    "hit_sec_extension_mismatch": "threat_extension_mismatch",
    "hit_sec_entropy": "threat_entropy",
    "hit_sec_tainted_injection": "threat_tainted_injection"
}

def rename_database_columns():
    if not DB_PATH.exists():
        print(f"❌ Error: Database not found at {DB_PATH}")
        sys.exit(1)

    print(f"📡 Connecting to {DB_PATH}...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Get existing columns
    cursor.execute("PRAGMA table_info(galactic_census)")
    existing_columns = [row[1] for row in cursor.fetchall()]

    renamed_count = 0
    not_found_count = 0

    print("\n⏳ Executing in-place column renames...\n")
    
    for old_col, new_col in RENAME_MAP.items():
        if old_col in existing_columns:
            try:
                # Execute the SQLite rename command
                cursor.execute(f"ALTER TABLE galactic_census RENAME COLUMN {old_col} TO {new_col}")
                print(f" ✅ Renamed: {old_col:<45} -> {new_col}")
                renamed_count += 1
            except sqlite3.OperationalError as e:
                print(f" ⚠️ Failed to rename {old_col}: {e}")
        elif new_col in existing_columns:
            print(f" ⏭️ Skipped:  {new_col} (Already renamed)")
        else:
            print(f" ❓ Missing:  {old_col} (Not found in database)")
            not_found_count += 1

    conn.commit()
    conn.close()

    print("\n" + "="*80)
    print(" 🛠️  DATABASE SCHEMA UPGRADE COMPLETE")
    print("="*80)
    print(f" Columns successfully renamed : {renamed_count}")
    print(f" Columns missing/skipped    : {not_found_count}")
    print("\nYour database is now perfectly aligned with the 49-key blueprint.")

if __name__ == "__main__":
    rename_database_columns()