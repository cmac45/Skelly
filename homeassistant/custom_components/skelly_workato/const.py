"""Constants for Skelly via Workato."""

import logging

DOMAIN = "skelly_workato"
LOGGER = logging.getLogger(__package__)

BASE_URL = "https://ai.workato.com/v1"

CONF_MAX_TOKENS = "max_tokens"

# The model name is the Workato router's name ("Skelly"), not a Claude model id:
# Workato decides which model it forwards to.
DEFAULT_MODEL = "Skelly"
DEFAULT_MAX_TOKENS = 200

# Fixed, not an option: anyone on the driveway can talk to this agent, so it gets
# Skelly's toolbox and never the Assist API (see skelly_tools).
LLM_API = "skelly_tools"
