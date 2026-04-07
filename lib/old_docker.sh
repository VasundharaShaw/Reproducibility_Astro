# #!/bin/bash

# # Build Docker image
# # build_docker_image() {
# #     log "[DOCKER] Building Docker image '$DOCKER_IMAGE_NAME'."

# #     local docker_err
# #     docker_err=$(docker build -t "$DOCKER_IMAGE_NAME" . 2>&1)
# #     ERROR_MSG=$(echo "$docker_err" | tail -n 20)


# #     if [ $? -ne 0 ]; then
# #         log "[ERROR] Docker build failed"
# #         log "[ERROR] $docker_err"
# #         DOCKER_BUILD_ERROR="$ERROR_MSG"
# #         return 1
# #     fi

# #     return 0
# # }

# DOCKER_ERROR_TYPE=""
# DOCKER_ERROR_MESSAGE=""


# create_dockerignore() {
#     log "[DOCKER] Creating .dockerignore in $REPO_NAME"

#     cat <<EOF > "$REPO_NAME/.dockerignore" 
# # Git directory
# .git
# .gitignore
# .gitattributes

# # Python cache
# __pycache__/
# *.py[cod]
# *$py.class
# *.so
# .Python
# pip-log.txt
# pip-delete-this-directory.txt
# .pytest_cache/
# .coverage
# htmlcov/

# # Virtual environments
# env/
# venv/
# ENV/
# env.bak/
# venv.bak/

# # Jupyter
# .ipynb_checkpoints/
# *.ipynb_checkpoints

# # IDE
# .vscode/
# .idea/
# *.swp
# *.swo
# *~
# .DS_Store

# # Build artifacts
# build/
# dist/
# *.egg-info/
# .eggs/

# # Documentation
# docs/
# documentation/



# # Other
# .cache/
# *.log
# .tmp/
# EOF
# }

# analyze_container_error() {
#     local log_file="$1"
#     local error_type="DOCKER_RUN_FAIL"
#     local error_message="Container execution failed"
    
#     # Priority order: check most specific errors first
    
#     # 1. Kernel errors
#     if grep -qi "NoSuchKernel\|No such kernel" "$log_file"; then
#         error_type="KERNEL_NOT_FOUND"
#         kernel_name=$(grep -oP "No such kernel named ['\"]?\K[^'\" \n]+" "$log_file" | head -1)
#         error_message="Jupyter kernel not found: ${kernel_name:-unknown kernel}"
    
#     # 2. Notebook execution errors
#     elif grep -qi "nbconvert.*failed\|Error executing notebook" "$log_file"; then
#         error_type="NOTEBOOK_EXECUTION_ERROR"
#         error_message="Failed to execute notebook"
    
#     # 3. Python import/dependency errors
#     elif grep -qi "ModuleNotFoundError" "$log_file"; then
#         error_type="MODULE_NOT_FOUND"
#         missing_module=$(grep -oP "ModuleNotFoundError: No module named ['\"]?\K[^'\" \n]+" "$log_file" | head -1)
#         error_message="Missing Python module: ${missing_module:-unknown}"
    
#     elif grep -qi "ImportError" "$log_file"; then
#         error_type="IMPORT_ERROR"
#         import_error=$(grep -oP "ImportError.*" "$log_file" | head -1 | cut -c1-200)
#         error_message="Python import error: ${import_error:-unknown}"
    
#     # 4. File system errors
#     elif grep -qi "FileNotFoundError" "$log_file"; then
#         error_type="FILE_NOT_FOUND"
#         missing_file=$(grep -oP "FileNotFoundError.*['\"]?\K[^'\" \n]+" "$log_file" | head -1)
#         error_message="File not found: ${missing_file:-unknown file}"
    
#     # 5. Permission errors
#     elif grep -qi "PermissionError\|Permission denied" "$log_file"; then
#         error_type="PERMISSION_ERROR"
#         error_message="Permission denied during execution"
    
#     # 6. Resource errors
#     elif grep -qi "MemoryError" "$log_file"; then
#         error_type="MEMORY_ERROR"
#         error_message="Out of memory error"
    
#     elif grep -qi "Killed\|OOMKilled" "$log_file"; then
#         error_type="CONTAINER_KILLED"
#         error_message="Container killed (likely out of memory)"
    
#     # 7. Timeout errors
#     elif grep -qi "TimeoutError\|timeout" "$log_file"; then
#         error_type="TIMEOUT_ERROR"
#         error_message="Execution timed out"
    
#     # 8. Syntax errors
#     elif grep -qi "SyntaxError" "$log_file"; then
#         error_type="SYNTAX_ERROR"
#         error_message="Python syntax error in notebook"
    
#     # 9. Network errors
#     elif grep -qi "ConnectionError\|ConnectionRefusedError\|URLError" "$log_file"; then
#         error_type="NETWORK_ERROR"
#         error_message="Network connection error"
    
#     # 10. Generic runtime errors
#     elif grep -qi "RuntimeError" "$log_file"; then
#         error_type="RUNTIME_ERROR"
#         runtime_msg=$(grep -oP "RuntimeError.*" "$log_file" | head -1 | cut -c1-200)
#         error_message="Runtime error: ${runtime_msg:-unknown}"
#     fi
    
#     # Return both error type and message
#     echo "${error_type}|${error_message}"
# }

# build_docker_image() {    
#     # Verify Dockerfile exists
#     if [ ! -f "$REPO_NAME/Dockerfile" ]; then
#         log "[ERROR]: Dockerfile not found in $REPO_NAME/"
#         return 1
#     fi
    
#     log "Repository directory found: $REPO_NAME"
#     # Check size of build context
#     log "[DOCKER] Analyzing build context size of $REPO_NAME..."        
    
    
#     # # Find large files
#     # log "Top 10 largest files/directories:"
#     # du -ah "$REPO_NAME" | sort -rh | head -20
    
#     # # Check .git size
#     # if [ -d "$REPO_NAME/.git" ]; then
#     #     git_size=$(du -sh "$REPO_NAME/.git" | cut -f1)
#     #     log "[DOCKER] .git directory size: $git_size"
#     # fi
#     # Show what we're about to send to Docker
#     # log "[DOCKER] Current directory: $(pwd)"
#     # log "[DOCKER] Current directory size: $(du -sh . 2>/dev/null | cut -f1)"

    
#     log "[DOCKER] Building Docker image from: $REPO_NAME/Dockerfile"
        
#     if ! DOCKER_BUILDKIT=0 docker build -f "$REPO_NAME/Dockerfile" -t "$DOCKER_IMAGE_NAME" . >> "$LOG_FILE" 2>&1; then
#         log "[ERROR] Error building Docker image. Skipping this repository..."
#         return 1
#     fi
#     docker_image_id=$(docker images --no-trunc --quiet "$DOCKER_IMAGE_NAME")
#     log "[DOCKER] docker_image_id: $docker_image_id"
#     docker_image_size=$(docker image inspect "$DOCKER_IMAGE_NAME" \
#         --format='{{.Size}}')

#     log "[DOCKER] docker_image_size: $docker_image_size"
#     docker_image_size_mb=$(echo "scale=2; $docker_image_size/1024/1024" | bc)
#     log "[DOCKER] docker_image_size_mb: $docker_image_size_mb"


# }

# # Run the Docker container with NOTEBOOK_PATHS passed as an environment variable
# run_docker_container() {    
#     log "[DOCKER] Running Docker container '$CONTAINER_NAME' with dynamic notebook paths..."
#     local container_log="$LOG_FILE.container"

#     # Run container and capture output
#     #docker run --user "$(id -u):$(id -g)" --name "$CONTAINER_NAME" -v "$(pwd)/logs:/app/logs" -v "$LOG_DIR:/logs" -v "$(pwd)/$REPO_NAME:/app" --env NOTEBOOK_PATHS="$NOTEBOOK_PATHS" --env SETUP_PATHS="$SETUP_PATHS" "$DOCKER_IMAGE_NAME" >> "$container_log" 2>&1
#     docker run --user "$(id -u):$(id -g)" --name "$CONTAINER_NAME" -v "$LOG_DIR:/logs" -v "$(pwd)/$REPO_NAME:/app" --env NOTEBOOK_PATHS="$NOTEBOOK_PATHS" --env SETUP_PATHS="$SETUP_PATHS" "$DOCKER_IMAGE_NAME" >> "$container_log" 2>&1
#     container_exit_code=$?

#      # Append container output to main log file
#     log "[DOCKER] =========================================="
#     log "[DOCKER] Container Output (exit code: $container_exit_code)"
#     log "[DOCKER] =========================================="
#     cat "$container_log" >> "$LOG_FILE"
#     log "[DOCKER] =========================================="
#     log "[DOCKER] End of Container Output"
#     log "[DOCKER] =========================================="

#     if [ $container_exit_code -ne 0 ]; then
#         log "[ERROR] Docker container exited with code: $container_exit_code"
        
#         # Analyze the error
#         error_info=$(analyze_container_error "$container_log")
#         error_type=$(echo "$error_info" | cut -d'|' -f1)
#         error_message=$(echo "$error_info" | cut -d'|' -f2-)
        
#         log "[ERROR] Detected error type: $error_type"
#         log "[ERROR] Error message: $error_message"
        
#         # Show last 20 lines of error for debugging
#         log "[ERROR] Last 20 lines of container output:"
#         tail -20 "$container_log" | while read line; do
#             log "[CONTAINER] $line"
#         done

        
        
#         DOCKER_ERROR_TYPE="$error_type"
#         DOCKER_ERROR_MESSAGE="$error_message"
#         #return 1

#     fi
#     # Cleanup
#     docker rm -f "$CONTAINER_NAME" >> "$LOG_FILE" 2>&1 || true
#     rm -f "$container_log"

    
#     log "[DOCKER] Container finished successfully"
#     rm -f "$container_log"
    
#     return 0


#     # if ! docker run --user "$(id -u):$(id -g)" --name "$CONTAINER_NAME" -v "$(pwd)/logs:/app/logs" -v "$(pwd)/$REPO_NAME:/app" --env NOTEBOOK_PATHS="$NOTEBOOK_PATHS" --env SETUP_PATHS="$SETUP_PATHS" "$DOCKER_IMAGE_NAME" >> "$LOG_FILE" 2>&1; then
#     #     log "[ERROR] Error running Docker container. Check the logs for details."
#     #     docker rm -f "$CONTAINER_NAME" >> "$LOG_FILE" 2>&1 || true
#     #     return 1
#     # fi
# }

# # Remove existing Docker container if it exists
# cleanup_container() {
    
#     if [ "$(docker ps -a -q -f name=^/${CONTAINER_NAME}$)" ]; then
#         log "[DOCKER] Removing existing Docker container '$CONTAINER_NAME'..."
#         docker rm -f "$CONTAINER_NAME" >> "$LOG_FILE" 2>&1
#         docker container prune -f
#     fi
# }

# create_dockerfile() {
#     log "[DOCKER] Creating Dockerfile in $REPO_NAME"

#     cat <<'EOF' > "$REPO_NAME/Dockerfile"
# FROM python:3.10-slim

# WORKDIR /app

# # Set HOME to avoid permission issues
# ENV HOME=/tmp

# RUN pip install --upgrade pip setuptools wheel --root-user-action=ignore
# RUN pip install jupyter nbdime --root-user-action=ignore


# COPY entrypoint.sh /entrypoint.sh
# RUN chmod +x /entrypoint.sh


# ENTRYPOINT ["/entrypoint.sh"]
# EOF

#     log "[DOCKER] Dockerfile created successfully."
# }
