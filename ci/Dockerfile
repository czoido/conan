FROM ubuntu:latest

LABEL maintainer="Conan.io <info@conan.io>"

ARG DEBIAN_FRONTEND=noninteractive

ENV PY38 3.8.6

# Install essential packages and dependencies for pyenv and other tools
RUN apt-get -qq update \
    && apt-get -qq install -y --no-install-recommends \
       sudo ca-certificates \
       make build-essential libssl-dev zlib1g-dev libbz2-dev \
       libreadline-dev libsqlite3-dev wget curl llvm libncurses5-dev libncursesw5-dev \
       xz-utils tk-dev libffi-dev liblzma-dev git \
    && rm -rf /var/lib/apt/lists/*

# Set up environment variables for pyenv
ENV PATH /home/runner/.pyenv/shims:/home/runner/.pyenv/bin:$PATH

# Install pyenv and Python version
RUN curl -L https://github.com/pyenv/pyenv-installer/raw/master/bin/pyenv-installer | bash \
    && pyenv init - \
    && pyenv virtualenv-init - \
    && pyenv update \
    && pyenv install $PY38 \
    && pyenv global $PY38

# Remove not needed packages except git
RUN apt-get -qq remove make build-essential gcc \
    && rm -rf /var/lib/apt/lists/*

# Check if the user 'runner' exists, if not, set necessary permissions
RUN if ! id -u runner > /dev/null 2>&1; then \
        adduser --disabled-password --gecos "" --uid 1001 runner; \
        groupadd docker --gid 123; \
        usermod -aG sudo runner; \
        usermod -aG docker runner; \
    fi \
    && echo "%sudo   ALL=(ALL:ALL) NOPASSWD:ALL" > /etc/sudoers \
    && echo "Defaults env_keep += \"DEBIAN_FRONTEND\"" >> /etc/sudoers

# Set up the work directory for the runner user
WORKDIR /home/runner

# Switch to the runner user, assuming it exists or was just created
USER runner
