"""Read-only Page-post visibility diagnostics. No create/edit/delete or token output."""
import argparse
import json
import re
from pathlib import Path
from facebook_feed.publisher import PageFeed,PublishError


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--post-suffix',required=True)
    parser.add_argument('--output',default='tmp/facebook-visibility/report.json')
    args=parser.parse_args(argv)
    if not re.fullmatch(r'[1-9]\d*',args.post_suffix):raise ValueError('Expected numeric post suffix, not a token or URL')
    client=PageFeed()
    report=client.inspect_visibility(client.page+'_'+args.post_suffix)
    destination=Path(args.output);destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(json.dumps(report,indent=2)+'\n')
    print('::notice::Page visibility check: '+json.dumps(report).replace('%','%25').replace('\n',' '))
    return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except (PublishError,ValueError) as error:
        print('::error::'+str(error).replace('%','%25').replace('\n',' '));raise SystemExit(1)
