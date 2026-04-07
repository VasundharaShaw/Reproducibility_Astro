#!/bin/bash


export GITHUB_REPO



ensure_pipeline_tables() {
    sqlite3 "$DB_FILE" <<EOF

-- =====================================================
-- 1️⃣ Repository Runs (Experiment-Level)
-- =====================================================
CREATE TABLE IF NOT EXISTS repository_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    repository_id INTEGER NOT NULL,
    url TEXT,

    run_status TEXT NOT NULL,           -- SUCCESS, DOCKER_BUILD_FAIL, DOCKER_RUN_FAIL
    error_message TEXT,

    started_at TEXT,
    finished_at TEXT,
    duration_seconds FLOAT,

    created_at TEXT DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (repository_id) REFERENCES repositories(id)
);


-- =====================================================
-- 2️⃣ Notebook Executions (Raw Execution Results)
-- =====================================================
CREATE TABLE IF NOT EXISTS notebook_executions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    repository_run_id INTEGER NOT NULL,
    repository_id INTEGER NOT NULL,
    notebook_id INTEGER NOT NULL,

    notebook_name TEXT,
    url TEXT,

    execution_status TEXT,              -- SUCCESS, FAILED, PARTIAL
    execution_duration FLOAT,

    total_code_cells INTEGER,
    executed_cells INTEGER,

    error_type TEXT,
    error_category TEXT,
    error_message TEXT,
    error_cell_index INTEGER,
    error_count INTEGER,

    created_at TEXT DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(repository_run_id, notebook_id),

    FOREIGN KEY (repository_run_id) REFERENCES repository_runs(id),
    FOREIGN KEY (repository_id) REFERENCES repositories(id),
    FOREIGN KEY (notebook_id) REFERENCES notebooks(id)
);


-- =====================================================
-- 3️⃣ Notebook Reproducibility Metrics (Comparison Layer)
-- =====================================================
CREATE TABLE IF NOT EXISTS notebook_reproducibility_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    repository_run_id INTEGER NOT NULL,
    notebook_execution_id INTEGER NOT NULL,

    repository_id INTEGER NOT NULL,
    notebook_id INTEGER NOT NULL,

    total_code_cells INTEGER,

    identical_cells_count INTEGER,
    different_cells_count INTEGER,
    nondeterministic_cells_count INTEGER,

    identical_cells TEXT,
    different_cells TEXT,
    nondeterministic_cells TEXT,

    reproducibility_score REAL,

    created_at TEXT DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(repository_run_id, notebook_id),

    FOREIGN KEY (repository_run_id) REFERENCES repository_runs(id),
    FOREIGN KEY (notebook_execution_id) REFERENCES notebook_executions(id),
    FOREIGN KEY (repository_id) REFERENCES repositories(id),
    FOREIGN KEY (notebook_id) REFERENCES notebooks(id)
);

EOF
}

create_repository_run() {
    local repo_id="$1"
    local repo_url="$2"

    RUN_ID=$(sqlite3 "$DB_FILE" <<EOF
INSERT INTO repository_runs (
    repository_id,
    url,
    run_status,
    started_at
) VALUES (
    $repo_id,
    '$repo_url',
    'RUNNING',
    datetime('now')
);
SELECT last_insert_rowid();
EOF
)

    export RUN_ID
}

finalize_repository_run() {
    
    log 'Updating repository_runs database table'
    local run_id="$1"
    local status="$2"
    local message="$3"
    local duration="$4"

    log "Run id: $run_id, Status : $status, Message: $message, Duration: $duration"

    sqlite3 "$DB_FILE" <<EOF
UPDATE repository_runs
SET
    run_status = '$status',
    error_message = '$message',
    finished_at = datetime('now'),
    duration_seconds = $duration
WHERE id = $run_id;
EOF
}


get_notebook_language_stats() {
    local repo_id="$1"

    sqlite3 "$DB_FILE" <<EOF
SELECT
    COUNT(*) AS total,
    SUM(CASE WHEN LOWER(language) = 'python' THEN 1 ELSE 0 END) AS python_count
FROM notebooks
WHERE repository_id = $repo_id;
EOF
}


# Move repository to repositories folder
move_repo() {    

    # Move the repository into the all_repos directory
    if [ -d "$REPO_NAME" ]; then
        log "[REPO] Moving repository '$REPO_NAME' to 'repositories' folder"
        rm -rf "$REPOS_DIR/$REPO_NAME"
        mv "$REPO_NAME" "$REPOS_DIR/"
    else
        log "[ERROR] Repository '$REPO_NAME' does not exist. Cannot move."
    fi   
    
}

sanitize_docker_name() {
    local name="$1"
    
    # Convert to lowercase
    name=$(echo "$name" | tr '[:upper:]' '[:lower:]')
    
    # Replace invalid characters with hyphens
    name=$(echo "$name" | sed 's/[^a-z0-9._-]/-/g')
    
    # Remove leading/trailing dots and hyphens
    name=$(echo "$name" | sed 's/^[.-]*//; s/[.-]*$//')
    
    # Replace multiple consecutive hyphens with single hyphen
    name=$(echo "$name" | sed 's/-\+/-/g')
    
    # Ensure name is not empty
    if [ -z "$name" ]; then
        name="unnamed"
    fi
    
    # Truncate to reasonable length (Docker allows up to 128 chars total)
    name=$(echo "$name" | cut -c1-60)
    
    echo "$name"
}

# Process the given repository
process_repo() {
    REPO_START_TIME=$(now_sec)

    GITHUB_REPO="$1"
    NOTEBOOK_PATHS="$2"
    SETUP_PATHS="$3"
    REQUIREMENT_PATHS="$4"

    REPO_NAME=$(basename "$GITHUB_REPO" .git)
    REPO_NAME_LOWER=$(echo "$REPO_NAME" | tr '[:upper:]' '[:lower:]')
    REPO_NAME_DOCKER=$(sanitize_docker_name "$REPO_NAME")

    log "[REPO] Repository: $REPO_NAME"
    log "[REPO] Docker-safe name: $REPO_NAME_DOCKER"

    # LOG_DIR="logs"
    # COMP_DIR="notebook_comparisons"
    # mkdir -p "$LOG_DIR" "$COMP_DIR"

    LOG_FILE="${LOG_DIR}/${REPO_NAME}.log"
    > "$LOG_FILE"

    export LOG_FILE

    create_repository_run "$REPO_ID" "$GITHUB_REPO"

    
    if ! validate_repo "$GITHUB_REPO"; then
        log "[REPO] Skipping $REPO_PATH due to invalid repository URL"

        REPO_TOTAL_TIME=$(elapsed_sec "$REPO_START_TIME")

        finalize_repository_run \
            "$RUN_ID" \
            "INVALID_REPOSITORY_URL" \
            "git ls-remote failed" \
            "$REPO_TOTAL_TIME"

        return 0
    fi

    stats=$(get_notebook_language_stats "$REPO_ID")

    total_notebooks=$(echo "$stats" | cut -d'|' -f1)
    python_notebooks=$(echo "$stats" | cut -d'|' -f2)

    log "[CHECK] Notebook stats for repo $GITHUB_REPO (id: $REPO_ID): total notebooks=$total_notebooks, python notebooks=$python_notebooks"

    if [ "$total_notebooks" -eq 0 ]; then
        log "[ERROR] Skipping $REPO_PATH: no notebooks found"
        REPO_TOTAL_TIME=$(elapsed_sec "$REPO_START_TIME")

        finalize_repository_run \
            "$RUN_ID" \
            "NO_NOTEBOOKS" \
            "Repository contains no notebooks" \
            "$REPO_TOTAL_TIME"
           
        return 0
    fi

    if [ "$python_notebooks" -eq 0 ]; then
        log "[ERROR] Skipping $REPO_PATH: no Python notebooks found"
        REPO_TOTAL_TIME=$(elapsed_sec "$REPO_START_TIME")

        finalize_repository_run \
            "$RUN_ID" \
            "NO_PYTHON_NOTEBOOKS" \
            "Repository contains only non-Python notebooks" \
            "$REPO_TOTAL_TIME"

        return 0
    fi


    # clone / pull
    if [ -d "$REPO_NAME" ]; then
        cd "$REPO_NAME" && git pull && cd ..
    else
        git clone --depth 1 "$GITHUB_REPO" >> "$LOG_FILE" 2>&1
    fi


    
    # requirements
    process_requirements
    # if [ -n "$REQUIREMENT_PATHS" ]; then
    #     combine_requirements_files 
    # else
    #     extract_requirements_from_nb
    # fi
    
    # ---------------- DOCKERFILE --------------------------
    DOCKER_IMAGE_NAME="jupyter_docker_image_$REPO_NAME_DOCKER"
    CONTAINER_NAME="jupyter_container_$REPO_NAME_DOCKER"

    # Verify names are valid
    if ! echo "$DOCKER_IMAGE_NAME" | grep -qE '^[a-z0-9][a-z0-9._-]*$'; then
        log "[ERROR] Invalid Docker image name: $DOCKER_IMAGE_NAME"
        log "[ERROR] Repository name contains invalid characters"
        return 1
    fi

    if [ ! -d "$REPO_NAME" ]; then
        log "[ERROR] Repository directory not found: $REPO_NAME"

        REPO_TOTAL_TIME=$(elapsed_sec "$REPO_START_TIME")

        finalize_repository_run \
            "$RUN_ID" \
            "REPO_DIR_MISSING" \
            "Repository directory not found before Docker build" \
            "$REPO_TOTAL_TIME"

        return 0
    fi


    create_entrypoint
    create_dockerfile
    create_dockerignore
    cleanup_container

    if ! build_docker_image; then        
        REPO_TOTAL_TIME=$(elapsed_sec "$REPO_START_TIME")

        finalize_repository_run \
            "$RUN_ID" \
            "DOCKER_BUILD_FAIL" \
            "Docker image build failed" \
            "$REPO_TOTAL_TIME"
        log "[ERROR] Skipping $REPO_PATH due to Docker build failure"
        return 0
    fi

    if ! run_docker_container; then
        REPO_TOTAL_TIME=$(elapsed_sec "$REPO_START_TIME")

        finalize_repository_run \
            "$RUN_ID" \
            "$DOCKER_ERROR_TYPE" \
            "$DOCKER_ERROR_MESSAGE" \
            "$REPO_TOTAL_TIME"

        return 0
    fi


    REPO_TOTAL_TIME=$(elapsed_sec "$REPO_START_TIME")
    NOTEBOOKS_COUNT=$(echo "$NOTEBOOK_PATHS" | awk -F';' '{print NF}')
    export REPO_TOTAL_TIME
    export NOTEBOOKS_COUNT

    # comparison
    compare_notebook_outputs

    
    # summary
    move_repo
    REPO_TOTAL_TIME=$(elapsed_sec "$REPO_START_TIME")   


    finalize_repository_run \
        "$RUN_ID" \
        "SUCCESS" \
        "Repository executed successfully" \
        "$REPO_TOTAL_TIME"


    log "[REPO] Total repository execution time: ${REPO_TOTAL_TIME}s."
    isExecutedSuccessfully="true"  
    export NOTEBOOKS_COUNT
    export RUN_ID

    
}

# Process all the repositories from the database
process_sqlite_flow() {
    # Fetch repository data from SQLite database
    # Initialize counter for successfully processed repos
    #processed_count=0
    processed_repo_ids=()
    #processed_repo_ids+=(16,6,9,10,14,16,18,19,20,24,26)
    #processed_repo_ids+=(3,6,8,9,10,11,14,16,17,25)
#     # Keep fetching and processing repos until we've successfully processed 5
#     while [ $processed_count -lt 15 ]; do
#         echo "processed_count: '$processed_count'"
#         # Build NOT IN clause from processed repo IDs
#         not_in_clause=""
#         if [ ${#processed_repo_ids[@]} -gt 0 ]; then
#             not_in_clause="AND id NOT IN ($(IFS=,; echo "${processed_repo_ids[*]}"))"
#         fi
    
#         # Query that excludes already processed repos using the array
#         repo_data=$(sqlite3 $DB_FILE <<EOF
# .mode csv
# .headers off
# SELECT id, repository, notebooks, setups, requirements 
# FROM repositories
# WHERE notebooks IS NOT NULL AND TRIM(notebooks) != '' AND notebooks_count != 0 $not_in_clause
# LIMIT 1;
# EOF
#        )
    local TARGET_COUNT=10
    local processed_count=0

    log "[INFO]: Processing next $TARGET_COUNT unexecuted repositories."    
    while [ $processed_count -lt $TARGET_COUNT ]; do
        if [ ${#processed_repo_ids[@]} -gt 0 ]; then
             not_in_clause="AND r.id NOT IN ($(IFS=,; echo "${processed_repo_ids[*]}"))"
        fi

#         repo_data=$(sqlite3 "$DB_FILE" <<EOF
# .mode csv
# .headers off
# SELECT
#     r.id,
#     r.repository,
#     r.notebooks,
#     r.setups,
#     r.requirements
# FROM repositories r
# WHERE
#     r.notebooks IS NOT NULL
#     AND TRIM(r.notebooks) != ''
#     AND r.notebooks_count != 0
#     AND r.id = 36
# ORDER BY r.id
# LIMIT 1;
# EOF
#         )
        repo_data=$(sqlite3 "$DB_FILE" <<EOF
.mode csv
.headers off
SELECT
    r.id,
    r.repository,
    r.notebooks,
    r.setups,
    r.requirements
FROM repositories r
WHERE
    r.notebooks IS NOT NULL
    AND TRIM(r.notebooks) != ''
    AND r.notebooks_count != 0
    AND r.id NOT IN (
        SELECT DISTINCT repository_id FROM repository_runs
    ) $not_in_clause
ORDER BY r.id
LIMIT 1;
EOF
        )

        # Exit loop if no more repos to process
        log "[INFO] REPO_DATA: $repo_data"
        if [ -z "$repo_data" ]; then
            log "[INFO] No more repositories to process"
            break
        fi


        # Process the repository
        IFS=',' read -r REPO_ID REPO_PATH NOTEBOOK_PATHS SETUP_PATHS REQUIREMENT_PATHS <<< "$repo_data"
        GITHUB_REPO="https://github.com/${REPO_PATH}"
        NOTEBOOK_PATHS=$(echo "$NOTEBOOK_PATHS" | tr -d '\r\n"') 
        REQUIREMENT_PATHS=$(echo "$REQUIREMENT_PATHS" | tr -d '\r\n"')
        SETUP_PATHS=$(echo "$SETUP_PATHS" | tr -d '\r\n"')

        log "[DEBUG]: REPO_ID='$REPO_ID'"
        log "[DEBUG]: GITHUB_REPO='$GITHUB_REPO'"
        log "[DEBUG]: REPO_PATH='$REPO_PATH'"
        log "[DEBUG]: NOTEBOOK_PATHS='$NOTEBOOK_PATHS'"

        processed_repo_ids+=($REPO_ID)

        isExecutedSuccessfully="false"
        # Process the repository from SQLite
        if ! process_repo "$GITHUB_REPO" "$NOTEBOOK_PATHS" "$SETUP_PATHS" "$REQUIREMENT_PATHS"; then
            log "[ERROR] Skipping $REPO_PATH due to failure"
            # Remove the repository folder if processing failed
            REPO_NAME=$(basename "$REPO_PATH")
            log "[DEBUG]: REPO_NAME='$REPO_NAME'"
            if [ -d "$REPO_NAME" ]; then
                rm -rf "$REPO_NAME"
                log "[ERROR] Removed failed repository folder: $REPO_NAME"
                processed_count=$((processed_count + 1))
            fi
            continue
        fi
        
        if [[ "$isExecutedSuccessfully" == "true" ]]; then
            # Add processed repo ID to array
            processed_count=$((processed_count + 1))
        fi
        # processed_count = 2    
    done
    
}
