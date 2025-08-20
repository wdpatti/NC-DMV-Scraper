#!/bin/bash

# Universal Docker Compose Deploy Script
# This script pulls the latest code and rebuilds/redeploys Docker containers

set -e  # Exit on any error

# Function to show usage
show_usage() {
    echo "Usage: $0 [container-name|all]"
    echo ""
    echo "Examples:"
    echo "  $0 nc-dmv-scraper    # Deploy specific container"
    echo "  $0 all               # Deploy all containers"
    echo "  $0                   # Interactive mode - will prompt for selection"
    echo ""
}

# Function to get available services from docker-compose.yml
get_services() {
    if [ -f "docker-compose.yml" ]; then
        docker-compose config --services 2>/dev/null || {
            echo "Error: Could not read docker-compose.yml services"
            exit 1
        }
    else
        echo "Error: docker-compose.yml not found in current directory"
        exit 1
    fi
}

# Function to deploy specific service
deploy_service() {
    local service_name="$1"
    
    echo "========================================="
    echo "Deploying: $service_name"
    echo "========================================="
    
    # Step 1: Navigate to the project directory
    echo "Step 1: Navigating to project directory..."
    cd NC-DMV-Scraper || {
        echo "Error: Could not find NC-DMV-Scraper directory"
        echo "Make sure you're running this script from the parent directory of NC-DMV-Scraper"
        exit 1
    }
    
    echo "Current directory: $(pwd)"
    
    # Step 2: Pull latest changes from git
    echo ""
    echo "Step 2: Pulling latest changes from git..."
    git pull || {
        echo "Error: Git pull failed"
        exit 1
    }
    
    # Step 3: Go back to parent directory
    echo ""
    echo "Step 3: Returning to parent directory..."
    cd ..
    
    echo "Current directory: $(pwd)"
    
    # Step 4: Build the Docker container
    echo ""
    echo "Step 4: Building Docker container: $service_name..."
    docker-compose build "$service_name" || {
        echo "Error: Docker build failed for $service_name"
        exit 1
    }
    
    # Step 5: Start the container in detached mode
    echo ""
    echo "Step 5: Starting container in detached mode: $service_name..."
    docker-compose up -d "$service_name" || {
        echo "Error: Docker compose up failed for $service_name"
        exit 1
    }
    
    echo ""
    echo "========================================="
    echo "Deployment completed successfully for: $service_name"
    echo "========================================="
}

# Function to deploy all services
deploy_all() {
    echo "========================================="
    echo "Deploying ALL containers"
    echo "========================================="
    
    # Step 1: Navigate to the project directory
    echo "Step 1: Navigating to project directory..."
    cd NC-DMV-Scraper || {
        echo "Error: Could not find NC-DMV-Scraper directory"
        echo "Make sure you're running this script from the parent directory of NC-DMV-Scraper"
        exit 1
    }
    
    echo "Current directory: $(pwd)"
    
    # Step 2: Pull latest changes from git
    echo ""
    echo "Step 2: Pulling latest changes from git..."
    git pull || {
        echo "Error: Git pull failed"
        exit 1
    }
    
    # Step 3: Go back to parent directory
    echo ""
    echo "Step 3: Returning to parent directory..."
    cd ..
    
    echo "Current directory: $(pwd)"
    
    # Step 4: Build all Docker containers
    echo ""
    echo "Step 4: Building all Docker containers..."
    docker-compose build || {
        echo "Error: Docker build failed"
        exit 1
    }
    
    # Step 5: Start all containers in detached mode
    echo ""
    echo "Step 5: Starting all containers in detached mode..."
    docker-compose up -d || {
        echo "Error: Docker compose up failed"
        exit 1
    }
    
    echo ""
    echo "========================================="
    echo "Deployment completed successfully for ALL containers!"
    echo "========================================="
}

# Main script logic
if [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
    show_usage
    exit 0
fi

# Get available services
available_services=$(get_services)

if [ $# -eq 0 ]; then
    # Interactive mode
    echo "Available services:"
    echo "$available_services" | nl -w2 -s'. '
    echo "$(echo "$available_services" | wc -l | awk '{print $1+1}'). all"
    echo ""
    echo -n "Select a service to deploy (number or name): "
    read -r selection
    
    if [[ "$selection" =~ ^[0-9]+$ ]]; then
        # Number selection
        total_services=$(echo "$available_services" | wc -l)
        if [ "$selection" -eq $((total_services + 1)) ]; then
            deploy_all
        elif [ "$selection" -ge 1 ] && [ "$selection" -le "$total_services" ]; then
            service_name=$(echo "$available_services" | sed -n "${selection}p")
            deploy_service "$service_name"
        else
            echo "Error: Invalid selection"
            exit 1
        fi
    elif [ "$selection" = "all" ]; then
        deploy_all
    else
        # Check if it's a valid service name
        if echo "$available_services" | grep -q "^$selection$"; then
            deploy_service "$selection"
        else
            echo "Error: '$selection' is not a valid service name"
            echo "Available services: $(echo "$available_services" | tr '\n' ' ')"
            exit 1
        fi
    fi
elif [ "$1" = "all" ]; then
    deploy_all
else
    # Check if the specified service exists
    if echo "$available_services" | grep -q "^$1$"; then
        deploy_service "$1"
    else
        echo "Error: '$1' is not a valid service name"
        echo "Available services: $(echo "$available_services" | tr '\n' ' ')"
        show_usage
        exit 1
    fi
fi

# Show running containers
echo ""
echo "Currently running containers:"
docker-compose ps

echo ""
echo "Useful commands:"
echo "  View logs: docker-compose logs -f [service-name]"
echo "  Stop containers: docker-compose down"
echo "  Restart container: docker-compose restart [service-name]"
