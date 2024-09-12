FROM ubuntu:latest

LABEL maintainer="Conan.io <info@conan.io>"

ARG DEBIAN_FRONTEND=noninteractive
ENV PY38 3.8.6

# Install basic dependencies for pyenv and other tools
RUN apt-get -qq update \
    && apt-get -qq install -y --no-install-recommends \
       sudo ca-certificates \
       # Required for pyenv
       make build-essential libssl-dev zlib1g-dev libbz2-dev \
       libreadline-dev libsqlite3-dev wget curl llvm libncurses5-dev libncursesw5-dev \
       xz-utils tk-dev libffi-dev liblzma-dev git


# Add 'runner' user similar to GitHub's runner user setup
RUN adduser --disabled-password --gecos "" --uid 1001 runner \
    && groupadd docker --gid 123 \
    && usermod -aG sudo runner \
    && usermod -aG docker runner \
    && echo "%sudo   ALL=(ALL:ALL) NOPASSWD:ALL" > /etc/sudoers \
    && echo "Defaults env_keep += \"DEBIAN_FRONTEND\"" >> /etc/sudoers

WORKDIR /home/runner

# Set PATH and install pyenv for the runner user
USER runner
ENV PATH /home/runner/.pyenv/shims:/home/runner/.pyenv/bin:$PATH

RUN curl -L https://github.com/pyenv/pyenv-installer/raw/master/bin/pyenv-installer | bash \
    && pyenv init - \
    && pyenv virtualenv-init - \
    && pyenv update \
    && pyenv install $PY38 \
    && pyenv global $PY38

# Clean up unnecessary build dependencies, but keep git
USER root
RUN apt-get -qq remove make build-essential gcc \
    && rm -rf /var/lib/apt/lists

USER runner
WORKDIR /home/runner
