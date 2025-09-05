#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2025 OliPi Project (Benoit Toufflet)

import os
import sys
from pathlib import Path
OLIPIMOODE_DIR = Path(__file__).resolve().parent
os.environ.setdefault("OLIPI_DIR", str(OLIPIMOODE_DIR))
from olipi_core.core_config import get_config
from olipi_core import core_common as core

core.screen.poweroff_safe()
sys.exit(0)
