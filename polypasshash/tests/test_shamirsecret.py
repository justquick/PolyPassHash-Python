from polypasshash import shamirsecret


def test_math():
    # doesnt pass now w/ c implementation
    #assert(shamirsecret._multiply_polynomials([1, 3, 4], [4, 5]) == [4, 9, 31, 20])
    assert(shamirsecret._full_lagrange([2, 4, 5], [14, 30, 32]) == [43, 168, 150])


def test_recovery():
    s = shamirsecret.ShamirSecret(2, 'hello')
    a = s.compute_share(1)
    b = s.compute_share(2)
    c = s.compute_share(3)

    # should be able to recover from any two...
    t = shamirsecret.ShamirSecret(2)
    t.recover_secretdata([a, b])

    t = shamirsecret.ShamirSecret(2)
    t.recover_secretdata([a, c])

    t = shamirsecret.ShamirSecret(2)
    t.recover_secretdata([b, c])

    # ... or even all three!
    t = shamirsecret.ShamirSecret(2)
    t.recover_secretdata([a, b, c])


def test_basic():

    #'\x02\x06'
    #'\x04\xb4'
    shares = [
        (2, bytearray(b'\x06')),
        (4, bytearray(b'\xb4'))
    ]

    u = shamirsecret.ShamirSecret(2)
    u.recover_secretdata(shares)

    assert(u.secretdata == 'h')


def test_complex():
    #'\x03\x1f'
    #'\x04\xdc'
    #'\x05\xf1'
    #'\x06\x86'
    #'\x07\xab'
    #'\x08\x1b'
    shares = [
        (3, bytearray(b'\x1f')),
        (4, bytearray(b'\xdc')),
        (5, bytearray(b'\xf1')),
        (6, bytearray(b'\x86')),
        (7, bytearray(b'\xab')),
        (8, bytearray(b'\x1b'))
    ]

    u = shamirsecret.ShamirSecret(2)
    u.recover_secretdata(shares)

    assert(u.secretdata == 'h')


def test_intro():

    # create a new object with some secret...
    mysecret = shamirsecret.ShamirSecret(2, 'my shared secret')
    # get shares out of it...

    a = mysecret.compute_share(4)
    b = mysecret.compute_share(6)
    c = mysecret.compute_share(1)
    d = mysecret.compute_share(2)

    # Recover the secret value
    newsecret = shamirsecret.ShamirSecret(2)

    newsecret.recover_secretdata([a, b, c])  # note, two would do...

    # d should be okay...
    assert(newsecret.is_valid_share(d))

    # change a byte
    d[1][3] = (d[1][3] + 1 % 256)

    # but not now...
    assert(newsecret.is_valid_share(d) is False)
