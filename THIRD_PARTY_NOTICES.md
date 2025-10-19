# Third-Party Notices

This file contains notices and information for third-party software included with or used by transcript-create.

## Software Dependencies

### Backend Dependencies (Python)

#### Core Framework and Web Server
- **FastAPI** - MIT License
  - Copyright (c) 2018 Sebastián Ramírez
  - https://github.com/tiangolo/fastapi

- **Uvicorn** - BSD-3-Clause License
  - Copyright (c) 2017-present, Encode OSS Ltd.
  - https://github.com/encode/uvicorn

#### Database
- **SQLAlchemy** - MIT License
  - Copyright (c) 2005-2024 Michael Bayer and contributors
  - https://github.com/sqlalchemy/sqlalchemy

- **psycopg** - GNU Lesser General Public License v3 (LGPLv3)
  - Copyright (C) 2020 The Psycopg Team
  - https://github.com/psycopg/psycopg

- **PostgreSQL** - PostgreSQL License
  - https://www.postgresql.org/about/licence/

#### Media Processing
- **yt-dlp** - The Unlicense (Public Domain)
  - https://github.com/yt-dlp/yt-dlp
  - Fork of youtube-dl

- **FFmpeg** - GNU Lesser General Public License v2.1+ (LGPLv2.1+) / GNU General Public License v2+ (GPLv2+)
  - Copyright (c) FFmpeg developers
  - https://ffmpeg.org/legal.html
  - Note: FFmpeg is dynamically linked and not distributed with this software. Users must install it separately.

#### Machine Learning and Transcription
- **faster-whisper** - MIT License
  - Copyright (c) 2023 Guillaume Klein
  - https://github.com/guillaumekln/faster-whisper
  - CTranslate2-based implementation of OpenAI's Whisper model

- **openai-whisper** - MIT License
  - Copyright (c) 2022 OpenAI
  - https://github.com/openai/whisper
  - PyTorch implementation of Whisper

- **pyannote.audio** - MIT License
  - Copyright (c) 2016-2024 CNRS
  - https://github.com/pyannote/pyannote-audio
  - Neural speaker diarization toolkit

- **PyTorch** - BSD-3-Clause License
  - Copyright (c) 2016-2024 Facebook, Inc. and its affiliates
  - https://github.com/pytorch/pytorch

- **NumPy** - BSD-3-Clause License
  - Copyright (c) 2005-2024, NumPy Developers
  - https://github.com/numpy/numpy

#### Configuration and Utilities
- **python-dotenv** - BSD-3-Clause License
  - Copyright (c) 2014, Saurabh Kumar
  - https://github.com/theskumar/python-dotenv

- **pydantic** - MIT License
  - Copyright (c) 2017 to present Pydantic Services Inc. and individual contributors
  - https://github.com/pydantic/pydantic

- **pydantic-settings** - MIT License
  - Copyright (c) 2017 to present Pydantic Services Inc. and individual contributors
  - https://github.com/pydantic/pydantic-settings

- **requests** - Apache License 2.0
  - Copyright 2019 Kenneth Reitz
  - https://github.com/psf/requests

#### Authentication and Payment
- **Authlib** - BSD-3-Clause License
  - Copyright (c) 2017 Hsiaoming Yang
  - https://github.com/lepture/authlib

- **stripe** - MIT License
  - Copyright (c) Stripe, Inc.
  - https://github.com/stripe/stripe-python

#### Document Generation
- **ReportLab** - BSD License
  - Copyright ReportLab Inc.
  - https://www.reportlab.com/
  - Note: Open source version used

### Frontend Dependencies (JavaScript/TypeScript)

#### Core Framework
- **React** - MIT License
  - Copyright (c) Meta Platforms, Inc. and affiliates
  - https://github.com/facebook/react

- **react-dom** - MIT License
  - Copyright (c) Meta Platforms, Inc. and affiliates
  - https://github.com/facebook/react

- **react-router-dom** - MIT License
  - Copyright (c) Remix Software Inc.
  - https://github.com/remix-run/react-router

#### Styling
- **Tailwind CSS** - MIT License
  - Copyright (c) Tailwind Labs, Inc.
  - https://github.com/tailwindlabs/tailwindcss

- **@tailwindcss/vite** - MIT License
  - Copyright (c) Tailwind Labs, Inc.
  - https://github.com/tailwindlabs/tailwindcss

#### Build Tools
- **Vite** - MIT License
  - Copyright (c) 2019-present, Yuxi (Evan) You and Vite contributors
  - https://github.com/vitejs/vite

- **@vitejs/plugin-react-swc** - MIT License
  - Copyright (c) 2019-present, Yuxi (Evan) You and Vite contributors
  - https://github.com/vitejs/vite-plugin-react-swc

#### HTTP Client
- **ky** - MIT License
  - Copyright (c) Sindre Sorhus
  - https://github.com/sindresorhus/ky

#### Development Tools
- **TypeScript** - Apache License 2.0
  - Copyright (c) Microsoft Corporation
  - https://github.com/microsoft/TypeScript

- **ESLint** - MIT License
  - Copyright OpenJS Foundation and other contributors
  - https://github.com/eslint/eslint

- **typescript-eslint** - BSD-2-Clause License
  - Copyright (c) 2019 typescript-eslint and other contributors
  - https://github.com/typescript-eslint/typescript-eslint

### GPU and Compute Platforms

#### ROCm (AMD GPU Computing Platform)
- **ROCm** - Multiple licenses (MIT, Apache 2.0, and others)
  - Copyright (c) Advanced Micro Devices, Inc.
  - https://github.com/RadeonOpenCompute/ROCm
  - Note: ROCm is not distributed with this software. Users with AMD GPUs must install it separately.

#### CUDA (NVIDIA GPU Computing Platform)
- **CUDA Toolkit** - NVIDIA Software License Agreement
  - Copyright (c) NVIDIA Corporation
  - https://developer.nvidia.com/cuda-toolkit
  - Note: CUDA is not distributed with this software. Users with NVIDIA GPUs must install it separately.

### Optional Dependencies

#### Search Backend
- **OpenSearch** - Apache License 2.0
  - Copyright OpenSearch Contributors
  - https://github.com/opensearch-project/OpenSearch
  - Note: Optional component; not required for core functionality

## Pre-trained Models and Data

### Whisper Models
- **Whisper** - MIT License
  - Copyright (c) 2022 OpenAI
  - https://github.com/openai/whisper
  - Pre-trained models available at: https://github.com/openai/whisper/blob/main/model-card.md
  - Model card and usage constraints: https://github.com/openai/whisper/blob/main/model-card.md
  - Training data includes public internet data; see model card for details
  - Users are responsible for ensuring compliance with model usage terms

### Pyannote Models
- **pyannote.audio models** - MIT License
  - Copyright (c) 2016-2024 CNRS
  - https://huggingface.co/pyannote
  - Requires Hugging Face token and acceptance of model terms
  - Users must accept model-specific terms on Hugging Face before use
  - Model cards available at: https://huggingface.co/pyannote/speaker-diarization-3.1

## Fonts

### PDF Export Font
- **DejaVu Fonts** - Bitstream Vera Fonts License / Public Domain
  - Copyright (c) 2003 by Bitstream, Inc.
  - https://dejavu-fonts.github.io/
  - License: https://dejavu-fonts.github.io/License.html
  - Note: Only included if PDF export functionality is used

## Container Images

### Base Docker Images
- **Ubuntu** - Multiple licenses (primarily GPLv3 and Apache 2.0)
  - Copyright (c) Canonical Ltd.
  - https://ubuntu.com/legal/intellectual-property-policy

- **rocm/dev-ubuntu** - Multiple licenses
  - Copyright (c) Advanced Micro Devices, Inc.
  - https://hub.docker.com/r/rocm/dev-ubuntu

## Important Notes

### Compliance and Usage

1. **Dynamic Linking**: Most dependencies are dynamically linked and not distributed as part of this repository's source code. Users install them via package managers (pip, npm).

2. **Model Usage**: Pre-trained ML models (Whisper, pyannote) have their own usage terms. Users must:
   - Review model cards and usage restrictions
   - Accept Hugging Face model terms where required
   - Ensure compliance with model licenses for their specific use case

3. **GPU Platforms**: ROCm and CUDA are not distributed with this software. Users must install the appropriate GPU computing platform separately based on their hardware.

4. **FFmpeg**: This software requires FFmpeg to be installed on the system. FFmpeg is licensed under LGPLv2.1+ or GPLv2+ depending on compile-time options. It is not included in this distribution.

5. **OpenSearch**: OpenSearch is an optional dependency for enhanced search functionality. If not used, the application falls back to PostgreSQL full-text search.

### License Compatibility

This project is licensed under the Apache License 2.0. All direct dependencies have licenses compatible with Apache 2.0, including:
- MIT License (permissive, compatible)
- BSD-3-Clause License (permissive, compatible)
- Apache License 2.0 (same license)
- The Unlicense (public domain, compatible)

Note: Some optional system dependencies (FFmpeg, psycopg) use LGPL or GPL licenses, but these are dynamically linked and not distributed with this codebase.

### Third-Party Service Providers

This application may integrate with:
- **YouTube** - Google Terms of Service apply when downloading content
- **Stripe** - Stripe Terms of Service apply for payment processing
- **Google OAuth** - Google API Terms apply for authentication
- **Twitch OAuth** - Twitch Developer Agreement applies for authentication
- **Hugging Face** - Hugging Face Terms apply when accessing models

Users are responsible for compliance with these third-party service terms.

## Updates

This notice file is current as of the date of this release. Dependencies may be updated over time. Users should review `requirements.txt` and `frontend/package.json` for the current list of direct dependencies.

For the most up-to-date license information, consult each dependency's repository or package metadata.

## Questions

If you have questions about third-party notices or licensing, please open an issue on the GitHub repository.
