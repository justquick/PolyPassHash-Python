import hashlib

# For thresholdless password support...
from Crypto.Cipher import AES

try:
    from . import fastshamirsecret as shamirsecret
except ImportError:
    from . import shamirsecret

import os

import pickle


class PolyPassHash(object):
    """
    This is a PolyHash object that has special routines for passwords
    """
    # this is keyed by user name.  Each value is a list of dicts (really a
    # struct) where each dict contains the salt, sharenumber, and
    # passhash (saltedhash XOR shamirsecretshare).
    accountdict = None

    # This contains the shamirsecret object for this data store
    shamirsecretobj = None

    # Is the secret value known?   In other words, is it safe to use the
    # passwordfile
    knownsecret = False

    # length of the salt in bytes
    saltsize = 16

    # hashing algorithm
    hasher = hashlib.sha256

    # number of bytes of data used for partial verification...
    partialbytes = 0

    # thresholdless support.   This could be random (and unknown) in the default
    # algorithm
    thresholdlesskey = None

    # number of used shares.   While I could duplicate shares for normal users,
    # I don't do so in this implementation.   This duplication would allow
    # co-analysis of password hashes
    nextavailableshare = None

    def __init__(self, threshold, passwordfile=None, partialbytes=0):

        self.threshold = threshold

        self.accountdict = {}

        self.partialbytes = partialbytes

        # creating a new password file
        if passwordfile is None:
            # generate a 256 bit key for AES.   I need 256 bits anyways
            # since I'll be XORing by the
            # output of SHA256, I want it to be 256 bits (or 32 bytes) long
            self.thresholdlesskey = os.urandom(32)
            # protect this key.
            self.shamirsecretobj = shamirsecret.ShamirSecret(threshold, self.thresholdlesskey)
            # I've generated it now, so it is safe to use!
            self.knownsecret = True
            self.nextavailableshare = 1
            return

        # Okay, they have asked me to load in a password file!
        self.shamirsecretobj = shamirsecret.ShamirSecret(threshold)
        self.knownsecret = False
        self.thresholdlesskey = None

        # A real implementation would need much better error handling
        passwordfiledata = open(passwordfile).read()

        # just want to deserialize this data.  Should do better validation
        self.accountdict = pickle.loads(passwordfiledata)

        assert(type(self.accountdict) is dict)

        # compute which share number is the largest used...
        for username in self.accountdict:
            # look at each share
            for share in self.accountdict[username]:
                self.nextavailableshare = max(self.nextavailableshare, share['sharenumber'])

        # ...then use the one after when I need a new one.
        self.nextavailableshare += 1

    def create_account(self, username, password, shares):
        """
        Creates a new account.
        Raises a ValueError if given bad data or if the system isn't initialized
        """

        if not self.knownsecret:
            raise ValueError("Password File is not unlocked!")

        if username in self.accountdict:
            raise ValueError("Username exists already!")

        # Were I to add support for changing passwords, etc. this code would be
        # moved to an internal helper.

        if shares > 255 or shares < 0:
            raise ValueError("Invalid number of shares: "+str(shares)+".")

        # Note this is just an implementation limitation.   I could do all sorts
        # of things to get around this (like just use a bigger field).
        if shares + self.nextavailableshare > 255:
            raise ValueError("Would exceed maximum number of shares: "+str(shares)+".")

        # for each share, we will add the appropriate dictionary.
        self.accountdict[username] = []

        if shares == 0:
            thisentry = {}
            thisentry['sharenumber'] = 0
            # get a random salt, salt the password and store the salted hash
            thisentry['salt'] = os.urandom(self.saltsize)
            saltedpasswordhash = self.hasher(thisentry['salt'] + password).digest()
            # Encrypt the salted secure hash.   The salt should make all entries
            # unique when encrypted.
            thisentry['passhash'] = AES.new(self.thresholdlesskey).encrypt(saltedpasswordhash)
            # technically, I'm supposed to remove some of the prefix here, but why
            # bother?

            # append the partial verification data...
            thisentry['passhash'] += saltedpasswordhash[len(saltedpasswordhash)-self.partialbytes:]

            self.accountdict[username].append(thisentry)
            # and exit (don't increment the share count!)
            return

        for sharenumber in range(self.nextavailableshare, self.nextavailableshare+shares):
            thisentry = {}
            thisentry['sharenumber'] = sharenumber
            # take the bytearray part of this
            shamirsecretdata = self.shamirsecretobj.compute_share(sharenumber)[1]
            thisentry['salt'] = os.urandom(self.saltsize)
            saltedpasswordhash = self.hasher(thisentry['salt'] + password).digest()
            # XOR the two and keep this.   This effectively hides the hash unless
            # threshold hashes can be simultaneously decoded
            thisentry['passhash'] = _do_bytearray_XOR(saltedpasswordhash, shamirsecretdata)
            # append the partial verification data...
            thisentry['passhash'] += saltedpasswordhash[len(saltedpasswordhash)-self.partialbytes:]

            self.accountdict[username].append(thisentry)

        # increment the share counter.
        self.nextavailableshare += shares

    def is_valid_login(self, username, password):
        """ Check to see if a login is valid."""

        if not self.knownsecret and self.partialbytes == 0:
            raise ValueError("Password File is not unlocked and partial verification is disabled!")

        if username not in self.accountdict:
            raise ValueError("Unknown user {0!r}".format(username))

        # I'll check every share.   I probably could just check the first in almost
        # every case, but this shouldn't be a problem since only admins have
        # multiple shares.   Since these accounts are the most valuable (for what
        # they can access in the overall system), let's be thorough.

        for entry in self.accountdict[username]:

            saltedpasswordhash = self.hasher(entry['salt'] + password).digest()

            # If not unlocked, partial verification needs to be done here!
            if not self.knownsecret:
                if saltedpasswordhash[len(saltedpasswordhash) - self.partialbytes:] == entry['passhash'][len(entry['passhash']) - self.partialbytes:]:
                    return True
                else:
                    return False

            # XOR to remove the salted hash from the password
            sharedata = _do_bytearray_XOR(saltedpasswordhash, entry['passhash'][:len(entry['passhash'])-self.partialbytes])

            # If a thresholdless account...
            if entry['sharenumber'] == 0:
                # return true if the password encrypts the same way...
                if AES.new(self.thresholdlesskey).encrypt(saltedpasswordhash) == entry['passhash'][:len(entry['passhash'])-self.partialbytes]:
                    return True
                # or false otherwise
                return False

            # now we should have a shamir share (if all is well.)
            share = (entry['sharenumber'], sharedata)

            # If a normal share, return T/F depending on if this share is valid.
            return self.shamirsecretobj.is_valid_share(share)

    def write_password_data(self, passwordfile):
        """ Persist the password data to disk."""
        if self.threshold >= self.nextavailableshare:
            raise ValueError("Would write undecodable password file.   Must have more shares before writing.")

        # Need more error checking in a real implementation
        with open(passwordfile, 'w') as f:
            pickle.dump(self.accountdict, f)

    def unlock_password_data(self, logindata):
        """Pass this a list of username, password tuples like: [('admin',
           'correct horse'), ('root','battery staple'), ('bob','puppy')]) and
           it will use this to access the password file if possible."""

        if self.knownsecret:
            raise ValueError("Password File is already unlocked!")
        # Okay, I need to find the shares first and then see if I can recover the
        # secret using this.

        sharelist = []

        for (username, password) in logindata:
            if username not in self.accountdict:
                raise ValueError("Unknown user '"+username+"'")

            for entry in self.accountdict[username]:

                # ignore thresholdless account entries...
                if entry['sharenumber'] == 0:
                    continue

                thissaltedpasswordhash = self.hasher(entry['salt']+password).digest()
                thisshare = (entry['sharenumber'], _do_bytearray_XOR(thissaltedpasswordhash, entry['passhash'][:len(entry['passhash']) - self.partialbytes]))

                sharelist.append(thisshare)

        # This will raise a ValueError if a share is incorrect or there are other
        # issues (like not enough shares).
        self.shamirsecretobj.recover_secretdata(sharelist)
        self.thresholdlesskey = self.shamirsecretobj.secretdata
        # it worked!
        self.knownsecret = True


#### Private helper...
def _do_bytearray_XOR(a, b):
    a = bytearray(a)
    b = bytearray(b)

    # should always be true in our case...
    if len(a) != len(b):
        print((len(a), len(b), a, b))
    assert(len(a) == len(b))
    result = bytearray()

    for pos in range(len(a)):
        result.append(a[pos] ^ b[pos])

    return result
