from enum import Enum


# The following code is CC BY-SA 4.0 by licensed as per Stack Overflow's conditions
# Source: https://stackoverflow.com/a/32313954/168735
# License: https://creativecommons.org/licenses/by-sa/4.0/
class AutoName(Enum):
    def _generate_next_value_(name, start, count, last_values):
        return name.lower()
