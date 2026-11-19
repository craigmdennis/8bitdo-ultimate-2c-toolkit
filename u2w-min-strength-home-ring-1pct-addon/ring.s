    .text
    .global ring
    .global maybe_off
    .global maybe_on
    .global setup

/* PB5 is the link light. Stock drives it as a GPIO, fully on or fully off.
   setup runs once, from the PWM init at 0xf71c, and leaves the pin on PWM5.
   ring only writes the compare word: 100 of period 10000 while the firmware
   wants the light on, and 0 while it wants it off. It does not call
   gpio_set_func and does not write the shared PWM clock. The blink hooks
   keep the return address in lr, because 0xf506 returns with tjex lr.
   Link at 0x1c990 with --defsym=gpio_set_func=0x129cc. */

ring:
    tcmp    r0, #0
    tjeq    duty_off
    tloadr  r0, duty_on
    tj      store
duty_off:
    tloadr  r0, duty_zero
store:
    tloadr  r3, pwm5
    tstorer r0, [r3, #0]
    tjex    lr

/* The blink sites call this with r0 = 0 or 1 and the old lr pushed. 0xf4d8
   returns through 0xf506 (tjex lr), so that lr has to be put back. */
blink_go:
    tjl     ring
    tpop    {r3}
    tmov    lr, r3
    tloadr  r3, ret_f506
    tjex    r3

maybe_off:
    tloadr  r1, pin
    tcmp    r3, r1
    tjne    stock_off
    tmovs   r0, #0
    tjl     ring
    tloadr  r0, ret_f5c0
    tmov    lr, r0
    tjex    lr
stock_off:
    tshftl  r3, r3, #16
    tshftr  r1, r3, #16
    tloadr  r0, ret_f5ce
    tmov    lr, r0
    tjex    lr

maybe_on:
    tloadr  r1, pin
    tcmp    r3, r1
    tjne    stock_on
    tmovs   r0, #1
    tjl     ring
    tloadr  r0, ret_f5c0
    tmov    lr, r0
    tjex    lr
stock_on:
    tshftl  r3, r3, #16
    tshftr  r2, r3, #16
    tloadr  r0, ret_f5ee
    tmov    lr, r0
    tjex    lr

/* Called with r3 pointing at the PWM enable register and r1 holding its byte,
   which is what 0xf71a just loaded. Replay the PWM4 enable bit, then set up PB5. */
setup:
    tpush   {lr}
    tmovs   r2, #16
    tor     r2, r1
    tshftl  r2, r2, #24
    tshftr  r2, r2, #24
    tstorerb r2, [r3, #0]
    tloadr  r0, pin
    tmovs   r1, #25
    tjl     gpio_set_func
    tloadr  r3, oen
    tloadrb r2, [r3, #0]
    tmovs   r1, #32
    tbclr   r2, r1
    tstorerb r2, [r3, #0]
    tloadr  r3, en
    tloadrb r2, [r3, #0]
    tmovs   r1, #32
    tor     r2, r1
    tstorerb r2, [r3, #0]
    tloadr  r0, duty_zero
    tloadr  r3, pwm5
    tstorer r0, [r3, #0]
    tpop    {pc}

    .align 2
pin:        .word 0x120
oen:        .word 0x80058a
en:         .word 0x800780
pwm5:       .word 0x8007a8
duty_on:    .word 0x27100064
duty_zero:  .word 0x27100000
ret_f5c0:   .word 0xf5c0
ret_f5ce:   .word 0xf5ce
ret_f5ee:   .word 0xf5ee
ret_f506:   .word 0xf506
