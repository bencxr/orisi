from collections import defaultdict
from shared.db_classes import TableDb, GeneralDb

import sqlite3
import time

ORACLE_FILE = 'oracle.db'

class OracleDb(GeneralDb):

  def __init__(self):
    self._filename = ORACLE_FILE
    self.connect()
    operations = {
      'TransactionRequest': TransactionRequestDb
    }
    self.operations = defaultdict(lambda: False, operations)


# XRequestDb - are classes for saving requests in history

class TransactionRequestDb(TableDb):
  """
  Used for saving transaction requests to DB (only requests,)
  """
  table_name = "transaction_requests"
  create_sql = "create table {0} ( \
    id integer primary key autoincrement, \
    ts datetime default current_timestamp, \
    from_address text not null, \
    json_data text not null);"
  insert_sql = "insert into {0} (from_address, json_data) values (?, ?)"

  def args_for_obj(self, obj):
    return [obj.from_address, obj.message]

class TaskQueue(TableDb):
  """
  Class responsible for saving transactions we're going to sign later.
  It accepts JSON, so we can add basically any task we'd like and parse
  it later.
  """

  table_name = "task_queue"
  
  create_sql = "create table {0} ( \
      id integer primary key autoincrement, \
      ts datetime default current_timestamp, \
      json_data text not null, \
      next_check integer not null, \
      filter_field text not null, \
      done integer default 0);"
  insert_sql = "insert into {0} (json_data, filter_field, next_check, done) values (?,?,?,?)"
  oldest_sql = "select * from {0} where next_check<? and done=0 order by ts limit 1"
  all_sql = "select * from {0} where next_check<? and done=0 order by ts"
  similar_sql = "select * from {0} where next_check<? and filter_field=? and done=0"
  mark_done_sql = "update {0} set done=1 where id=?"

  def args_for_obj(self, obj):
    return [obj["json_data"], obj['filter_field'], obj["next_check"], obj["done"]]

  def get_oldest_task(self):
    cursor = self.db.get_cursor()
    sql = self.oldest_sql.format(self.table_name)

    row = cursor.execute(sql, (int(time.time()), )).fetchone()
    if row:
      row = dict(row)
    return row

  def get_all_tasks(self):
    cursor = self.db.get_cursor()
    sql = self.all_sql.format(self.table_name)

    rows = cursor.execute(sql, (int(time.time()), )).fetchall()
    rows = [dict(row) for row in rows]
    return rows

  def get_similar(self, task):
    cursor = self.db.get_cursor()
    sql = self.similar_sql.format(self.table_name)

    rows = cursor.execute(sql, (int(time.time()), task['filter_field'])).fetchall()
    rows = [dict(row) for row in rows]
    return rows

  def done(self, task):
    cursor = self.db.get_cursor()
    sql = self.mark_done_sql.format(self.table_name)
    cursor.execute(sql, (int(task['id']), ))

class UsedInput(TableDb):
  """
  Class that adds what transaction we want to sign. When new transaction comes through with
  same address, but different inputs and outputs we won't sign it!
  """
  table_name = "used_input"
  create_sql = "create table {0} ( \
      id integer primary key autoincrement, \
      ts datetime default current_timestamp, \
      input_hash text unique, \
      json_out text not null);"
  insert_sql = "insert or ignore into {0} (input_hash, json_out) values (?, ?)"
  exists_sql = "select * from {0} where input_hash=?"
  def args_for_obj(self, obj):
    return [obj["input_hash"], obj["json_out"]]

  def get_input(self, i):
    sql = self.exists_sql.format(self.table_name)
    cursor = self.db.get_cursor()
    row = cursor.execute(sql, (i, ) ).fetchone()
    if row:
      result = dict(row)
      return result
    else:
      return None


class SignedTransaction(TableDb):
  """
  Class that will keep all transactions signed by oracle (possible multiplications for now)
  """
  table_name = "signed_transaction"
  create_sql = "create table {0} ( \
      id integer primary key autoincrement, \
      ts datetime default current_timestamp, \
      hex_transaction text not null, \
      prevtx text not null)"
  insert_sql = "insert into {0} (hex_transaction, prevtx) values (?, ?)"

  def args_for_obj(self, obj):
    return [obj["hex_transaction"], obj["prevtx"]]


class HandledTransaction(TableDb):
  """
  Class that will take care of keeping information which txid were already handled
  and how many signatures they got
  """
  talbe_name = "handled_tx"
  create_sql = "create table {0} ( \
      id integer primary key autoincrement, \
      ts datetime default current_timestamp, \
      txid text unique, \
      max_sigs integer not null);"
  insert_sql = "insert or replace into {0} (txid, max_sigs) values (?,?)"
  tx_sql = "select max_sigs from {0} where txid=?"

  def args_for_obj(self, obj):
    return [obj['txid'], obj['max_sigs']]

  def signs_for_transaction(self, txid):
    cursor = self.db.get_cursor()
    sql = self.tx_sql.format(self.table_name)

    row = cursor.execute(sql, (txid, )).fetchone()
    if row:
      row = dict(row)
      return row['max_sigs']
    else:
      sql = self.insert_sql.format(self.table_name)
      cursor.execute(sql, (txid, 0))
    return 0

  def update_tx(self, txid, sigs):
    self.save({"txid":txid, "max_sigs":sigs})



