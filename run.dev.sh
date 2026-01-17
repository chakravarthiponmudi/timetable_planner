#!/bin/bash

# Abort on any error
set -e

CONTAINER_NAME="timetable-dev"

# Stop and remove existing container if it exists
if docker container inspect "$CONTAINER_NAME" > /dev/null 2>&1; then
    echo "Stopping and removing existing container..."
    docker stop "$CONTAINER_NAME"
    docker rm "$CONTAINER_NAME"
fi

# Build the docker image
echo "Building dev docker image..."
docker build -t timetable-planner-dev -f Dockerfile.dev .

# Run the docker container
echo "Running dev container..."
docker run -d \
  -p 8080:80 \
  --name "$CONTAINER_NAME" \
  -v "$(pwd)/timetable-server":/app/server \
  -v "$(pwd)/timetable-ui":/app/ui \
  timetable-planner-dev

echo "Container '$CONTAINER_NAME' is running."
echo "Application available at http://localhost:8080"
echo "To see logs, run: docker logs -f $CONTAINER_NAME"

