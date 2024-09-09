FROM ubuntu:focal

LABEL maintainer="Conan.io <info@conan.io>"

ARG DEBIAN_FRONTEND=noninteractive

ENV PY38 3.8.6

RUN apt-get -qq update \
    && apt-get -qq install -y --no-install-recommends \
       sudo ca-certificates \
       # pyenv requires
       make build-essential libssl-dev zlib1g-dev libbz2-dev \
       libreadline-dev libsqlite3-dev wget curl llvm libncurses5-dev libncursesw5-dev \
       xz-utils tk-dev libffi-dev liblzma-dev python-openssl git \
    && useradd -ms /bin/bash conan \
    && mkdir -p /home/conan \
    && chown -R conan:conan /home/conan \
    && chown -R conan:conan /__w 

USER conan
WORKDIR /home/conan
ENV PATH /home/conan/.pyenv/shims:/home/conan/.pyenv/bin:$PATH
RUN curl -L https://github.com/pyenv/pyenv-installer/raw/master/bin/pyenv-installer | bash \
    && pyenv init - \
    && pyenv virtualenv-init - \
    && pyenv update \
    && pyenv install $PY38 \
    && pyenv global $PY38

# Remove not needed things except git
USER root
RUN apt-get -qq remove make build-essential gcc \
    && rm -rf /var/lib/apt/lists
    
USER conan
WORKDIR /home/conan
