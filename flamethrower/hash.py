def fnv1_32_hash(data: bytes):
    k_offset = 5381
    k_prime = 33

    hash_value = k_offset

    for byte in data:
        hash_value = (hash_value * k_prime) ^ byte

    return hash_value & 0xFFFFFFFF


def fnv1a_32_hash(data: bytes):
    k_offset = 5381
    k_prime = 33

    hash_value = k_offset

    for byte in data:
        hash_value = (hash_value ^ byte) * k_prime

    return hash_value & 0xFFFFFFFF


def fnv1_64_hash(data: bytes):
    k_offset = 14695981039346656037
    k_prime = 1099511628211

    hash_value = k_offset

    for byte in data:
        hash_value = (hash_value * k_prime) ^ byte

    return hash_value


def fnv1a_64_hash(data: bytes):
    k_offset = 14695981039346656037
    k_prime = 1099511628211

    hash_value = k_offset

    for byte in data:
        hash_value = (hash_value ^ byte) * k_prime

    return hash_value
