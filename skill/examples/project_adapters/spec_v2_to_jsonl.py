"""PROJECT-SPECIFIC recorded SPEC v2 fixture adapter; not a generic wire decoder."""
from pathlib import Path
import argparse,json
def main():
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    words=[int(x,16) for x in a.input.read_text().split()]
    if len(words)%2065:raise ValueError('SPEC v2 fixture packet count')
    rows=[];last_drop=0
    for i in range(0,len(words),2065):
        w=words[i:i+2065]
        if w[0]!=0x53504543 or w[1]!=0x20040 or w[2]!=8260:raise ValueError('not the historical SPEC v2 contract')
        rows.append({'sequence':w[3],'first_sample':w[4]|(w[5]<<32),'sample_count':w[15],
                     'bins':[v>>16 for v in w[16:]],'values':[v&65535 for v in w[16:]],
                     'errors':w[10]|w[14],'reference_peak':{'bin':w[12]>>16,'value':w[12]&65535},'whole_frame_drop':w[11]>last_drop})
        last_drop=w[11]
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text('\n'.join(json.dumps(x) for x in rows)+'\n',encoding='utf-8')
    print('Normalized complete recorded packets:',len(rows))
if __name__=='__main__':main()
