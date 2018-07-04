import os
from argparse import ArgumentParser

from scripts.ucca_db2 import get_by_xids, get_most_recent_passage_by_uid
from ucca import convert
from ucca.ioutil import write_passage

desc = "Download passages to old UCCA annotation app"


def download_passage(xid, **kwargs):
    passages = get_by_xids(xids=[xid], **kwargs)
    return convert.from_site(passages[0])


def download_most_recent_passage_by_uid(uid, passage_id, **kwargs):
    passage = get_most_recent_passage_by_uid(uid, passage_id, **kwargs)
    return convert.from_site(passage)


def main(args):
    os.makedirs(args.outdir, exist_ok=True)
    kwargs = dict(db_name=args.db_name, host_name=args.host_name)
    with open(args.filename, encoding="utf-8") as f:
        for passage_id, id_field in map(str.split, f):
            if args.verbose:
                print("Getting passage " + passage_id + " from user " + id_field)
            if args.method == "xid":
                passage = download_passage(id_field, **kwargs)
            elif args.method == "uid":
                passage = download_most_recent_passage_by_uid(id_field, passage_id, **kwargs)
            else:
                raise ValueError("Unknown method: '%s'" % args.method)
            write_passage(passage, outdir=args.outdir, verbose=args.verbose)


if __name__ == "__main__":
    argparser = ArgumentParser(description=desc)
    argparser.add_argument("filename", help="specification filename with (passage ID, xid OR uid) per passage")
    argparser.add_argument("--method", required=True, choices=("xid", "uid"), help="Get by xid or latest by paid, uid")
    argparser.add_argument("-d", "--db-name", default="work", help="database name")
    argparser.add_argument("-H", "--host-name", default="pgserver", help="host name")
    argparser.add_argument("-o", "--outdir", default=".", help="directory to write created XML IDs to")
    argparser.add_argument("-v", "--verbose", action="store_true", help="print tagged text for each passage")
    main(argparser.parse_args())
