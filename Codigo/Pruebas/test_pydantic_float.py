from pydantic import BaseModel
from typing import Optional

class TestModel(BaseModel):
    precio: Optional[float] = None

try:
    m1 = TestModel(**{"precio": ""})
    print("Empty string works:", m1.precio)
except Exception as e:
    print("Empty string fails:", e)
