with m.Case("00 --- 100"): # INR
with m.Case("00 --- 101"): # DCR
with m.Case("00 110 110"): # MVI M, data
with m.Case("00 --- 110"): # MVI r, data
with m.Case("00 --0 001"): # LXI
with m.Case("00 --1 001"): # DAD
with m.Case("00 --0 011"): # INX
with m.Case("00 --1 011"): # DCX
with m.Case("00 0-- 111"): # Accumulator Bit Rotations
with m.Case("00 0-0 010"): # STAX
with m.Case("00 0-1 010"): # LDAX
with m.Case("00 1-- 010"): # Direct Addressing block
with m.Case("00 101 111"): # CMA
with m.Case("00 11- 111"): # Carry Bit block

with m.Case("01 --- ---"): # MOV r, r 
with m.Case("01 --- 110"): # MOV r, M
with m.Case("01 110 ---"): # MOV M, r 
with m.Case("01 110 110"): # HLT

with m.Case("10 --- ---"): # ALU op block

with m.Case("11 --- 00-"): # Return Block
with m.Case("11 --- 010"): # Jump Condtitional block
with m.Case("11 --- 100"): # Call conditional block
with m.Case("11 --- 110"): # Immediate ALU group
with m.Case("11 --- 111"): # RST
with m.Case("11 --0 001"): # POP
with m.Case("11 --0 101"): # PUSH
with m.Case("11 01- 011"): # IN/OUT
with m.Case("11 100 011"): # XTHL
with m.Case("11 101 001"): # PCHL
with m.Case("11 101 011"): # XCHG
with m.Case("11 11- 011"): # EI/DI
with m.Case("11 111 001"): # SPHL