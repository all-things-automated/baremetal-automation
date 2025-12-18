# Spacelift Runner Image for Bare-Metal Automation
# Purpose: Execute Ansible playbooks for bare-metal lifecycle management
# Base: Spacelift's official runner with Terraform and common tools

FROM public.ecr.aws/spacelift/runner-terraform:latest

# Metadata
LABEL maintainer="infrastructure@site.com"
LABEL description="Ansible runner for bare-metal server discovery and lifecycle management"
LABEL version="1.0.0"

# Switch to root to install packages
USER root

# Install Ansible and system dependencies (Alpine packages)
RUN apk add --no-cache \
        python3 \
        py3-pip \
        openssh-client \
        git \
        sshpass \
        gcc \
        python3-dev \
        musl-dev \
        libffi-dev \
        openssl-dev \
        cargo \
        rust

# Upgrade pip and install build tools
RUN pip3 install --upgrade pip setuptools wheel

# Copy requirements files
COPY requirements.txt /tmp/requirements.txt
COPY requirements.yml /tmp/requirements.yml

# Install Python packages (Ansible dependencies)
RUN pip3 install --no-cache-dir -r /tmp/requirements.txt

# Install Ansible Core
RUN pip3 install --no-cache-dir ansible-core>=2.16.0

# Install Ansible Collections
RUN ansible-galaxy collection install -r /tmp/requirements.yml

# Create directory for Ansible execution
RUN mkdir -p /opt/ansible

# Set working directory
WORKDIR /mnt/workspace

# Ansible configuration will be used from repository (ansible.cfg)
# Credentials provided via environment variables at runtime

# Health check - verify Ansible is installed
RUN ansible --version && \
    ansible-galaxy collection list

# Default command (overridden by Spacelift)
CMD ["/bin/bash"]
