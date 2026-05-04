#!/bin/bash
###############################################################################
# repo.sh — Per-repository orchestration and batch SQLite flow
#
# Reads repo list from:   data/db.sqlite        (DB_FILE)
# Writes results to:      output/db/db.sqlite   (OUTPUT_DB_FILE)
###############################################################################

export GITHUB_REPO

# -----------------------------------------------------------------------------
# create_repository_run()
# Inserts a new run record into OUTPUT_DB_FILE. Sets global RUN_ID.
# -----------------------------------------------------------------------------
create_repository_run() {
    RUN_ID=$(sqlite3 "$OUTPUT_DB_FILE" <<EOF
INSERT INTO repository_runs (repository_id, url, run_status, started_at)
VALUES ($1, '$2', 'RUNNING', datetime('now'));
SELECT last_insert_rowid();
EOF
)
    export RUN_ID
}

# -----------------------------------------------------------------------------
# finalize_repository_run()
# Updates a run record in OUTPUT_DB_FILE with final status and duration.
# -----------------------------------------------------------------------------
finalize_repository_run() {
    log "[REPO] Finalizing run $1 — status: $2"
    sqlite3 "$OUTPUT_DB_FILE" <<EOF
UPDATE repository_runs
SET run_status='$2', error_message='$3', finished_at=datetime('now'), duration_seconds=$4
WHERE id=$1;
EOF
}

# -----------------------------------------------------------------------------
# get_notebook_language_stats()
# Counts total and Python notebooks for a repo in OUTPUT_DB_FILE.
# -----------------------------------------------------------------------------
get_notebook_language_stats() {
    sqlite3 "$OUTPUT_DB_FILE" <<EOF
SELECT COUNT(*), SUM(CASE WHEN LOWER(language)='python' THEN 1 ELSE 0 END)
FROM notebooks WHERE repository_id=$1;
EOF
}

# -----------------------------------------------------------------------------
# get_or_create_repo_id()
# Looks up or inserts a repo record in OUTPUT_DB_FILE. Returns the row id.
# -----------------------------------------------------------------------------
get_or_create_repo_id() {
    local repo_path="${1#https://github.com/}"
    local existing_id
    existing_id=$(sqlite3 "$OUTPUT_DB_FILE" "SELECT id FROM repositories WHERE repository='$repo_path' LIMIT 1;")
    if [ -n "$existing_id" ]; then echo "$existing_id"; return 0; fi
    sqlite3 "$OUTPUT_DB_FILE" <<EOF
INSERT INTO repositories (repository, notebooks, setups, requirements, notebooks_count, setups_count, requirements_count)
VALUES ('$repo_path', '$NOTEBOOK_PATHS', '$SETUP_PATHS', '$REQUIREMENT_PATHS', 0, 0, 0);
SELECT last_insert_rowid();
EOF
}

# -----------------------------------------------------------------------------
# discover_notebooks()
# Finds all .ipynb files in a cloned repo. Sets NOTEBOOK_PATHS (semicolon-
# separated, relative to repo root) and updates notebooks_count in OUTPUT_DB_FILE.
# -----------------------------------------------------------------------------
discover_notebooks() {
    local repo_dir="$1"
    local repo_id="$2"

    log "[NOTEBOOK] Discovering notebooks in $repo_dir..."

    local notebooks
    notebooks=$(find "$repo_dir" -name "*.ipynb" \
        ! -path "*/.ipynb_checkpoints/*" \
        ! -name "*_output.ipynb" \
        | sed "s|$repo_dir/||" \
        | sort)

    if [ -z "$notebooks" ]; then
        log "[NOTEBOOK] No notebooks found in $repo_dir."
        NOTEBOOK_PATHS=""
        return 1
    fi

    NOTEBOOK_PATHS=$(echo "$notebooks" | tr '\n' ';' | sed 's/;$//')
    local count
    count=$(echo "$notebooks" | wc -l | xargs)

    log "[NOTEBOOK] Found $count notebook(s): $NOTEBOOK_PATHS"

    # Update notebooks column and count in OUTPUT_DB_FILE
    sqlite3 "$OUTPUT_DB_FILE" <<EOF
UPDATE repositories
SET notebooks='$NOTEBOOK_PATHS', notebooks_count=$count
WHERE id=$repo_id;
EOF

    # Insert each notebook into the notebooks table so comparison can find it
    while IFS= read -r nb_path; do
        [ -z "$nb_path" ] && continue
        safe_path=$(echo "$nb_path" | sed "s/'/''/g")
        sqlite3 "$OUTPUT_DB_FILE" "INSERT OR IGNORE INTO notebooks (repository_id, name, language) VALUES ($repo_id, '$safe_path', 'python');"
    done <<< "$notebooks"

    log "[NOTEBOOK] Inserted $count notebook record(s) into DB."

    export NOTEBOOK_PATHS
    return 0
}

# -----------------------------------------------------------------------------
# process_repo()
# Full per-repo flow: validate → clone → discover notebooks → setup env →
# run notebooks → compare outputs.
# -----------------------------------------------------------------------------
process_repo() {
    REPO_START_TIME=$(now_sec)
    GITHUB_REPO="$1"; NOTEBOOK_PATHS="$2"; SETUP_PATHS="$3"; REQUIREMENT_PATHS="$4"
    REPO_NAME=$(basename "$GITHUB_REPO" .git)
    REPO_DIR="$REPOS_DIR/$REPO_NAME"

    log "[REPO] ── Starting: $REPO_NAME ──────────────────────────────"
    LOG_FILE="${LOG_DIR}/${REPO_NAME}.log"; > "$LOG_FILE"; export LOG_FILE

    create_repository_run "$REPO_ID" "$GITHUB_REPO"

    # 1. Validate
    if ! validate_repo "$GITHUB_REPO"; then
        finalize_repository_run "$RUN_ID" "INVALID_REPOSITORY_URL" "git ls-remote failed" "$(elapsed_sec "$REPO_START_TIME")"
        return 0
    fi

    # 2. Clone or pull
    if [ -d "$REPO_DIR" ]; then
        log "[REPO] Repo already exists, pulling latest..."
        cd "$REPO_DIR" && git pull >> "$LOG_FILE" 2>&1 && cd - > /dev/null
    else
        log "[REPO] Cloning into $REPO_DIR..."
        git clone --depth 1 "$GITHUB_REPO" "$REPO_DIR" >> "$LOG_FILE" 2>&1
    fi

    if [ ! -d "$REPO_DIR" ]; then
        finalize_repository_run "$RUN_ID" "REPO_DIR_MISSING" "Directory not found after clone" "$(elapsed_sec "$REPO_START_TIME")"
        return 0
    fi

    # 3. Discover notebooks (populate NOTEBOOK_PATHS)
    if ! discover_notebooks "$REPO_DIR" "$REPO_ID"; then
        finalize_repository_run "$RUN_ID" "NO_NOTEBOOKS" "No notebooks found in repo" "$(elapsed_sec "$REPO_START_TIME")"
        return 0
    fi

    # 4. Check for Python notebooks
    # stats=$(get_notebook_language_stats "$REPO_ID")
    # total_notebooks=$(echo "$stats" | cut -d'|' -f1)
    # python_notebooks=$(echo "$stats" | cut -d'|' -f2)
    # log "[REPO] Notebooks: total=$total_notebooks python=$python_notebooks"

    # if [ "${python_notebooks:-0}" -eq 0 ]; then
    #     finalize_repository_run "$RUN_ID" "NO_PYTHON_NOTEBOOKS" "No Python notebooks found" "$(elapsed_sec "$REPO_START_TIME")"
    #     return 0
    # fi

    # 4. Log notebook count (language check skipped — assume Python)
    log "[REPO] Notebooks found: $(echo "$NOTEBOOK_PATHS" | awk -F';' '{print NF}')"
    # 5. Process requirements
    process_requirements

    # 6. Set up Python environment
    REQUIREMENTS_FILE="$REPO_DIR/requirements.txt"
    if ! setup_pyenv_env "$REPO_DIR" "$REQUIREMENTS_FILE" "$SETUP_PATHS"; then
        finalize_repository_run "$RUN_ID" "$ENV_ERROR_TYPE" "$ENV_ERROR_MESSAGE" "$(elapsed_sec "$REPO_START_TIME")"
        cleanup_pyenv_env; return 0
    fi

    # 7. Run notebooks
    if ! run_in_pyenv_env "$REPO_DIR"; then
        analyze_env_error "$LOG_FILE"
        finalize_repository_run "$RUN_ID" "$ENV_ERROR_TYPE" "$ENV_ERROR_MESSAGE" "$(elapsed_sec "$REPO_START_TIME")"
        cleanup_pyenv_env; return 0
    fi

    # 8. Compare outputs
    NOTEBOOKS_COUNT=$(echo "$NOTEBOOK_PATHS" | awk -F';' '{print NF}')
    export NOTEBOOKS_COUNT
    compare_notebook_outputs
    cleanup_pyenv_env

    local total_time
    total_time=$(elapsed_sec "$REPO_START_TIME")
    finalize_repository_run "$RUN_ID" "SUCCESS" "Repository executed successfully" "$total_time"
    log "[REPO] ── Done: $REPO_NAME (${total_time}s) ──────────────────────"
    isExecutedSuccessfully="true"
    export RUN_ID NOTEBOOKS_COUNT
}

# -----------------------------------------------------------------------------
# process_sqlite_flow()
# Batch mode: reads unprocessed repos from DB_FILE (data/db.sqlite),
# checks OUTPUT_DB_FILE to skip already-processed ones.
# -----------------------------------------------------------------------------
process_sqlite_flow() {
    processed_repo_ids=()
    local processed_count=0
    log "[BATCH] Processing next $TARGET_COUNT unprocessed repositories."

    while [ $processed_count -lt "$TARGET_COUNT" ]; do
        local not_in_clause=""
        if [ ${#processed_repo_ids[@]} -gt 0 ]; then
            not_in_clause="AND r.id NOT IN ($(IFS=,; echo "${processed_repo_ids[*]}"))"
        fi

        # Read next repo from input DB_FILE.
        # Only process git-hosted repos (github). Zenodo and personal sites
        # are skipped here — they will be handled by a dedicated download
        # stage added later.
        # WHERE 1=1 ensures the AND clauses below are always valid.
        repo_data=$(sqlite3 "$DB_FILE" <<EOF
.mode csv
.headers off
SELECT r.id, r.repository
FROM repositories r
WHERE 1=1
  AND (r.host_type = 'github' OR r.host_type IS NULL)
$not_in_clause
ORDER BY r.id LIMIT 1;
EOF
)

        if [ -z "$repo_data" ]; then log "[BATCH] No more repositories."; break; fi

        IFS=',' read -r INPUT_REPO_ID REPO_PATH <<< "$repo_data"
        REPO_PATH=$(echo "$REPO_PATH" | tr -d '\r\n"')

        # Guard: only prepend github.com if it's not already a full URL
        if [[ "$REPO_PATH" == http* ]]; then
            GITHUB_REPO="$REPO_PATH"
        else
            GITHUB_REPO="https://github.com/${REPO_PATH}"
        fi

        log "[BATCH] Repo $INPUT_REPO_ID: $GITHUB_REPO"

        # Get or create repo record in OUTPUT_DB_FILE
        NOTEBOOK_PATHS=""; SETUP_PATHS=""; REQUIREMENT_PATHS=""
        REPO_ID=$(get_or_create_repo_id "$GITHUB_REPO")
        export REPO_ID

        # Check if already processed in output DB
        if [ -z "$REPO_ID" ]; then
            log "[BATCH] Could not get repo ID, skipping."
            processed_repo_ids+=("$INPUT_REPO_ID")
            continue
        fi
        already_run=$(sqlite3 "$OUTPUT_DB_FILE" "SELECT COUNT(*) FROM repository_runs WHERE repository_id=$REPO_ID;")
        if [ "$already_run" -gt 0 ]; then
            log "[BATCH] Repo $REPO_ID already processed, skipping."
            processed_repo_ids+=("$INPUT_REPO_ID")
            continue
        fi

        processed_repo_ids+=("$INPUT_REPO_ID")
        isExecutedSuccessfully="false"

        if ! process_repo "$GITHUB_REPO" "$NOTEBOOK_PATHS" "$SETUP_PATHS" "$REQUIREMENT_PATHS"; then
            REPO_NAME=$(basename "$REPO_PATH")
            [ -d "$REPOS_DIR/$REPO_NAME" ] && rm -rf "$REPOS_DIR/$REPO_NAME"
            processed_count=$((processed_count + 1))
            continue
        fi
        [[ "$isExecutedSuccessfully" == "true" ]] && processed_count=$((processed_count + 1))
    done
    log "[BATCH] Finished. Processed $processed_count repositories."
}