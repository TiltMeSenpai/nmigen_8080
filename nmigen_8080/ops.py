from enum import Enum

class OpBlock(Enum):
    # Possible decoder op blocks
    # Drive from core state machine, never read
    # This results in synth optimizing this out
    DECODE = 1
    CARRY_BIT = 2
    INR = 3
    DCR = 4
    CMA = 5
    DAA = 6
    HLT = 7
    MOV_r_M = 8
    MOV_M_r = 9
    MOV_r_r = 10
    STAX = 11
    LDAX = 12
    ALU_REG = 13
    BIT_ROT = 14
    PUSH = 15
    POP = 16
    DAD = 17
    INX = 18
    DCX = 19
    XCHG = 20
    XTHL = 21
    SPHL = 22
    MVI_M_i = 23
    MVI_r_i = 24
    ALU_IMM = 25
    LXI = 26
    DIRECT = 27
    PCHL = 28
    JMP = 29
    JMP_COND = 30
    CALL = 31
    CALL_COND = 32
    RET = 33
    RET_COND = 34
    RST = 35
    EI_DI = 36
    IO = 37
    NOP = 38