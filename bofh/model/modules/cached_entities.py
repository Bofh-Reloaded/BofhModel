class CachedEntities:
    def __init__(self, db):
        self.db = db
        self.__exchanges = {}
        self.__tokens = {}
        self.__pools = {}

    @property
    def coin_name(self):
        return "BNB"

    def get_exchange(self, id):
        try:
            return self.__exchanges[id]
        except KeyError:
            pass
        with self.db as curs:
            self.__exchanges[id] = curs.get_exchange(id=id)
            return self.__exchanges[id]

    def get_token(self, address_or_id):
        try:
            return self.__tokens[address_or_id]
        except KeyError:
            pass
        with self.db as curs:
            if isinstance(address_or_id, int):
                self.__tokens[address_or_id] = curs.get_token(id=address_or_id)
            else:
                self.__tokens[address_or_id] = curs.get_token(address=address_or_id)
            return self.__tokens[address_or_id]

    def get_pool(self, address):
        try:
            return self.__pools[address]
        except KeyError:
            pass
        with self.db as curs:
            self.__pools[address] = curs.get_pool(address=address)
            return self.__pools[address]

    def amount_hr(self, amount, token):
        return "%0.4f" % token.fromWei(amount)

    def get_pool_name(self, pool):
        s0 = "?"
        s1 = "?"
        try:
            s0 = self.get_token(pool.token0_id).get_symbol()
        except:
            pass
        try:
            s1 = self.get_token(pool.token1_id).get_symbol()
        except:
            pass
        return "%s-%s" % (s0, s1)

    def get_pool_tokens(self, pool):
        return self.get_token(pool.token0_id), self.get_token(pool.token1_id)
