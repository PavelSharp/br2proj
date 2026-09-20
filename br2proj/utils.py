#Python 3.12: ReadableBuffer (like hashlib)

#==[TRI CUSTOM HASH FUNCTION]==
# [NEW 20.09.2026] 
# Reverse engineering of the Infernal Engine reveals that Terminal Reality
# used a custom hashing function for all internal string indexing.
# At runtime, the engine discards string buffers by converting
# them into uint32 hashes for fast table lookups across major subsystems.
# It features a case-insensitive, iterative MAD hash design.
# The implementation is based on sub_786230.
def tri_hash(bts: bytes | bytearray | str, init : int = 0) : #init : int32->uint32
    if isinstance(bts, str): bts = bts.encode('ascii', errors='strict')
    signedi32 = ((init + 0x80000000) % 0x100000000) - 0x80000000
    val = signedi32 & 0xFFFFFFFFFFFFFFFF
    for b in bts :
        b = b - 32 if 97 <= b <= 122 else b # type: ignore
        val = (((val + b) * 314159821) & 0xFFFFFFFFFFFFFFFF) % 0xFFFFFFFB # type: ignore
    return val & 0xFFFFFFFF

# ==[Native C implementation]== 
# Precise fixed-width integer types eliminate the need for 
# complex type-wrapping required by Python's infinite ints.
# static inline uint32_t tri_hash(const char* bts, int32_t init = 0) {
#     uint64_t val = (uint64_t)init;
#     for (int i = 0; bts[i]; ++i) {
#         uint8_t b = (uint8_t)bts[i];
#         if (b >= 97 && b <= 122) b -= 32;
#         val = ((val + b) * 314159821) % 0xFFFFFFFBULL;
#     }
#     return (uint32_t)val;
# }