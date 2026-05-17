class A:
    def add(self, a, b):
        return a + b

class B:
    def compute(self, a: int, b: int) -> int:
        print(f"Computing {a} + {b} in Class B...")
        return a + b