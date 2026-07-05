import sqlite3
import os

DB_PATH = os.path.join('fleet_management', 'db.sqlite3')

def main():
    if not os.path.exists(DB_PATH):
        print('DB file not found:', DB_PATH)
        return
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute('pragma wal_checkpoint(full);')
        conn.close()
        print('WAL checkpointed')
    except Exception as e:
        print('Checkpoint error:', e)

    for suf in ['-wal', '-shm']:
        f = DB_PATH + suf
        try:
            if os.path.exists(f):
                os.remove(f)
                print('Removed', f)
            else:
                print('Not present', f)
        except Exception as e:
            print('Could not remove', f, e)

if __name__ == '__main__':
    main()
