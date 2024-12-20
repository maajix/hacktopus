from dataclasses import dataclass
from typing import Protocol


class ValidationHandler(Protocol):
    def is_expired(self) -> bool:
        ...


@dataclass
class Date:
    day: int
    month: int
    year: int


@dataclass
class CreditCard:
    number: int
    expiration: str
    cvv: str
    date: Date
    validator: ValidationHandler

    def validate(self):
        if self.validator.is_expired():
            print("Card is expired")
        else:
            print("Card is valid")
