import pandas as pd
from databroker import Broker

db = Broker.named('hxn')


# wrapper for two databases
class Broker_New(Broker):

    def __getitem__(self, key):
        try:
            return db_new[key]
        except ValueError:
            return db_old[key]

    def get_table(self, *args, **kwargs):
        result_old = db_old.get_table(*args, **kwargs)
        result_new = db_new.get_table(*args, **kwargs)
        result = [result_old, result_new]
        return pd.concat(result)

    def get_images(self, *args, **kwargs):
        result_old = db_old.get_images(*args, **kwargs)
        result_new = db_new.get_images(*args, **kwargs)
        result = [result_old, result_new]
        return pd.concat(result)

    def get_events(self, *args, **kwargs):
        result_old = db_old.get_events(*args, **kwargs)
        result_new = db_new.get_events(*args, **kwargs)
        result = [result_old, result_new]
        return pd.concat(result)

    def retrieve(self, *args, **kwargs):
        try:
            db_new.reg.retrieve(*args, **kwargs)
        except DatumNotFound:
            db_old.reg.retrieve(*args, **kwargs)


db = Broker_New.named('hxn')
