"""API request and response models: ports."""

import pydantic


class PortOut(pydantic.BaseModel):
    """A port we serve."""

    model_config = pydantic.ConfigDict(from_attributes=True)

    code: str
    name: str
    country: str
    region: str
    is_hub: bool
