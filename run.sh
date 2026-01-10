#!/bin/bash

IMAGE_NAME="timetable-app"
CONTAINER_NAME="timetable-app-container"
DOCKERFILE_PATH="dockerFile" # Assuming dockerFile is in the current directory

# Stop and remove any existing container with the same name
echo "Stopping and removing existing container (if any)..."
docker stop ${CONTAINER_NAME} > /dev/null 2>&1
docker rm ${CONTAINER_NAME} > /dev/null 2>&1

# Build the Docker image
echo "Building Docker image: ${IMAGE_NAME}"
docker build --no-cache -t ${IMAGE_NAME} -f ${DOCKERFILE_PATH} .
# Check if build was successful
if [ $? -ne 0 ]; then
    echo "Docker image build failed!"
    exit 1
fi

# Run the Docker container
echo "Running Docker container: ${CONTAINER_NAME} on port 8080"
docker run -d --name ${CONTAINER_NAME} -p 3000:3000 ${IMAGE_NAME}

# Check if run was successful
if [ $? -ne 0 ]; then
    echo "Docker container failed to start!"
    exit 1
fi

echo "Container ${CONTAINER_NAME} is running. Access the UI at http://localhost:8080"
echo "To stop the container, run: docker stop ${CONTAINER_NAME}"
echo "To remove the container, run: docker rm ${CONTAINER_NAME}"
echo "To remove the image, run: docker rmi ${IMAGE_NAME}"
