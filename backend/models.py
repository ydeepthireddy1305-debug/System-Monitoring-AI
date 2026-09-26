from pydantic import BaseModel


class Metrics(BaseModel):
    cpu: float
    ram: float
    disk: float
    bytes_sent: int
    bytes_received: int