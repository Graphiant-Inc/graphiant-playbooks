# Stage 1: Build stage
FROM python:3.12-slim AS builder
WORKDIR /app

# Copy collection and install dependencies
COPY ansible_collections /app/ansible_collections
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir -r /app/ansible_collections/graphiant/naas/requirements-ee.txt

# Install the Ansible collection
RUN ansible-galaxy collection install /app/ansible_collections/graphiant/naas/ --force

# Stage 2: Final stage
FROM python:3.12-slim
ARG COMMIT_SHA=dev
WORKDIR /app

# Copy virtual environment and collection
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /root/.ansible/collections /root/.ansible/collections
COPY --from=builder /app/ansible_collections /app/ansible_collections

# Install system tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    vim \
    git \
    sshpass \
    && rm -rf /var/lib/apt/lists/*

# Set environment
ENV PATH="/opt/venv/bin:$PATH"
ENV GRAPHIANT_NAAS_VERSION=$COMMIT_SHA

# Copy additional project files
COPY README.md LICENSE ./
COPY terraform ./terraform/

CMD ["/bin/bash"]
