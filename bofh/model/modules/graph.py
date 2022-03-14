import bofh_model_ext


class TheGraph:
    def __init__(self, status_db, attacks_db = None):
        self.graph = bofh_model_ext.TheGraph()
        self.__db = status_db
        self.__attacks_db = attacks_db
        self.graph.set_fetch_exchange_tag_cb(self.__fetch_exchange_cb)
        self.graph.set_fetch_token_tag_cb(self.__fetch_token_cb)
        self.graph.set_fetch_lp_tag_cb(self.__fetch_lp_cb)
        self.graph.set_fetch_lp_reserves_tag_cb(self.__fetch_lp_reserves_cb)
        self.graph.set_fetch_path_tag_cb(self.__fetch_path_cb)
        self.graph.set_fetch_token_addr_cb(self.__fetch_token_addr_cb)
        self.graph.set_fetch_lp_addr_cb(self.__fetch_lp_addr_cb)

    def __fetch_exchange_cb(self, id):
        with self.__db as curs:
            vals = curs.get_exchange_vals(id)
            try:
                return self.graph.add_exchange(*vals)
            except:
                return None

    def __fetch_token_cb(self, id):
        with self.__db as curs:
            vals = curs.get_topic_vals(id)
            try:
                return self.graph.add_token(*vals)
            except:
                return None

    def __fetch_lp_cb(self, id):
        with self.__db as curs:
            vals = curs.get_lp_vals(id)
            try:
                return self.graph.add_lp(*vals)
            except:
                return None

    def __fetch_lp_reserves_cb(self, pool):
        with self.__db as curs:
            vals = curs.get_lp_reserves_vals(pool.tag)
            try:
                pool.setReserves(*vals)
            except:
                pass
            return pool

    def __fetch_path_cb(self, path_hash):
        if not self.__attacks_db:
            return None
        with self.__attacks_db as curs:
            pool_ids = list(curs.get_attack_pool_ids(path_hash))
            try:
                return self.graph.add_path(*pool_ids)
            except:
                return None

    def __fetch_token_addr_cb(self, addr):
        with self.__db as curs:
            vals = curs.get_topic_vals_by_addr(addr)
            try:
                return self.graph.add_token(*vals)
            except:
                return None

    def __fetch_lp_addr_cb(self, addr):
        with self.__db as curs:
            vals = curs.get_lp_vals_by_addr(addr)
            try:
                return self.graph.add_lp(*vals)
            except:
                return None

    def get_constraint(self):
        return bofh_model_ext.PathEvalutionConstraints()



