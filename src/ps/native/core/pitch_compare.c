/* SPDX-License-Identifier: AGPL-3.0-or-later
 * Numerical ports/adaptations of MTG sms-tools TWM_p/peakInterp and
 * Essentia PitchSalienceFunction/PitchYinFFT.
 * Copyright (C) 2006-2021 Music Technology Group - Universitat Pompeu Fabra
 * Candidate integration and C port, 2026. See REFERENCES.md and references/.
 * No temporal smoothing, no final instrument classification, no note segmentation.
 * Static workspace: single caller only. No malloc and no raw-PCM FFT.
 */
#include "pitch_compare.h"
#include <math.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#define PI_F 3.14159265358979323846f
#define FS_F 16000.0f
#define BIN_HZ (FS_F/PITCH_N)
static float real_fft[PITCH_N], imag_fft[PITCH_N];
static float tw_re[PITCH_N/2], tw_im[PITCH_N/2], yin_weight[PITCH_BINS];
static float norm_mag[PITCH_BINS], sort_work[PITCH_BINS];
static float peak_freq[PITCH_MAX_PEAKS], peak_mag[PITCH_MAX_PEAKS], peak_db[PITCH_MAX_PEAKS];
static float candidates[PITCH_MAX_PEAKS*4], salience_curve[PITCH_SALIENCE_BINS], yin_curve[PITCH_BINS];
static int npeaks, initialized;
static const float mask_hz[34]={0,20,25,31.5f,40,50,63,80,100,125,160,200,250,315,400,500,
    630,800,1000,1250,1600,2000,2500,3150,4000,5000,6300,8000,9000,10000,12500,15000,20000,25100};
static const float mask_db[34]={-75.8f,-70.1f,-60.8f,-52.1f,-44.2f,-37.5f,-31.3f,-25.6f,
    -20.9f,-16.5f,-12.6f,-9.6f,-7,-4.7f,-3,-1.8f,-.8f,-.2f,0,.5f,1.6f,3.2f,5.4f,7.8f,
    8.1f,5.3f,-2.4f,-11.1f,-12.8f,-12.2f,-7.4f,-17.8f,-17.8f,-17.8f};
static float clampf(float x,float lo,float hi) {return x<lo?lo:(x>hi?hi:x);}
static int cmp_float(const void *a,const void *b) {float x=*(const float*)a,y=*(const float*)b;return (x>y)-(x<y);}
static void blank(PitchResult *r,int reason) {memset(r,0,sizeof(*r));r->midi=-1;r->reason=reason;}
static void finish(PitchResult *r,float f,float score,int valid,int mode)
{
    r->frequency=f; r->score=score; r->valid=valid; r->mode=mode;
    r->reason=valid?PITCH_OK:PITCH_NO_ESTIMATE;
    r->midi=valid?(int)floorf(69.0f+12.0f*log2f(f/440.0f)+.5f):-1;
}
void PitchDefaultConfig(PitchConfig *c)
{
    c->min_hz=27.0f;c->max_hz=4300.0f;c->min_peak=20.0f;c->min_peak_median_ratio=6.0f;
    c->relative_peak_db=40.0f;c->peak_floor=2.0f;c->twm_max_error=10.0f;
    c->yin_min_confidence=.8f;c->twm_subharmonics=0;c->yin_first_minimum=1;
}
void PitchInit(void)
{
    int i,j;
    for(i=0;i<PITCH_N/2;i++) {tw_re[i]=cosf(-2*PI_F*i/PITCH_N);tw_im[i]=sinf(-2*PI_F*i/PITCH_N);}
    for(i=0,j=1;i<PITCH_BINS;i++) {
        float f=i*BIN_HZ,w;
        while(j<33 && f>mask_hz[j]) j++;
        w=mask_db[j-1]+(mask_db[j]-mask_db[j-1])*(f-mask_hz[j-1])/(mask_hz[j]-mask_hz[j-1]);
        yin_weight[i]=powf(10.0f,w/20.0f); /* matches Essentia db2lin(weight/2) */
    }
    initialized=1;
}
static void fft_forward(void)
{
    unsigned i,j=0,len;
    for(i=1;i<PITCH_N;i++) {
        unsigned bit=PITCH_N>>1;
        while(j&bit) {j^=bit;bit>>=1;} j^=bit;
        if(i<j) {float t=real_fft[i];real_fft[i]=real_fft[j];real_fft[j]=t;
                 t=imag_fft[i];imag_fft[i]=imag_fft[j];imag_fft[j]=t;}
    }
    for(len=2;len<=PITCH_N;len<<=1) {
        unsigned half=len>>1,step=PITCH_N/len,base,k;
        for(base=0;base<PITCH_N;base+=len) for(k=0;k<half;k++) {
            unsigned a=base+k,b=a+half,t=k*step;
            float vr=real_fft[b]*tw_re[t]-imag_fft[b]*tw_im[t];
            float vi=real_fft[b]*tw_im[t]+imag_fft[b]*tw_re[t];
            real_fft[b]=real_fft[a]-vr;imag_fft[b]=imag_fft[a]-vi;
            real_fft[a]+=vr;imag_fft[a]+=vi;
        }
    }
}
float PitchTwmCore(const float *freq,const float *db,int count,const float *cand,int nc,float *error)
{
    int i,j,h,n=count<10?count:10,best=0;
    float maxdb=-1e30f,amp[PITCH_MAX_PEAKS],inv[PITCH_MAX_PEAKS],besterr=1e30f;
    *error=besterr;
    if(count<1 || count>PITCH_MAX_PEAKS || nc<1) return 0;
    for(i=0;i<count;i++) {if(freq[i]<=0 || !isfinite(freq[i]) || !isfinite(db[i])) return 0;if(db[i]>maxdb) maxdb=db[i];}
    for(i=0;i<count;i++) {amp[i]=powf(10,(db[i]-maxdb)/20);inv[i]=1/sqrtf(freq[i]);}
    for(i=0;i<nc;i++) {
        float pm=0,mp=0;
        if(cand[i]<=0 || !isfinite(cand[i])) continue;
        for(h=1;h<=n;h++) {
            float harmonic=cand[i]*h,diff=1e30f,pd;int nearest=0;
            for(j=0;j<count;j++) {float d=fabsf(harmonic-freq[j]);if(d<diff) {diff=d;nearest=j;}}
            pd=diff/sqrtf(harmonic);
            pm+=pd+amp[nearest]*(1.4f*pd-.5f);
        }
        for(j=0;j<n;j++) {
            float nh=floorf(freq[j]/cand[i]+.5f),pd;
            if(nh<1) nh=1;
            pd=fabsf(freq[j]-nh*cand[i])*inv[j];
            mp+=amp[j]*(pd+amp[j]*(1.4f*pd-.5f));
        }
        pm=pm/n+.33f*mp/n;
        if(pm<besterr) {besterr=pm;best=i;}
    }
    *error=besterr;return besterr<1e30f?cand[best]:0;
}
int PitchSalienceCore(const float *freq,const float *mag,int count,float min_hz,float max_hz,float *curve)
{
    int i,h,b,bins;
    float mx=0,weights[20],kernel[11];
    if(!isfinite(min_hz)||!isfinite(max_hz)||min_hz<=0||max_hz<=min_hz||count<0||count>PITCH_MAX_PEAKS)return 0;
    bins=(int)floor(120.0*log2((double)max_hz/min_hz))+1;
    if(bins>PITCH_SALIENCE_BINS || bins<3) return 0;
    memset(curve,0,bins*sizeof(float));
    for(h=0;h<20;h++) weights[h]=powf(.8f,(float)h);
    for(b=0;b<=10;b++) {float v=cosf(b*PI_F/20);kernel[b]=v*v;}
    for(i=0;i<count;i++) {if(freq[i]<=0 || mag[i]<=0 || !isfinite(freq[i]) || !isfinite(mag[i])) return 0;if(mag[i]>mx)mx=mag[i];}
    for(i=0;i<count;i++) {
        if(mag[i]<=mx*.01f)continue;
        for(h=0;h<20;h++) {
            /* Double precision here avoids crossing a 10-cent rounding boundary
             * due only to float division/log rounding; histogram remains float. */
            int hb=(int)floor(120.0*log2((double)freq[i]/((h+1)*(double)min_hz))+.5);
            int lo=hb-10,hi=hb+10;
            if(hb<0) break;
            if(lo<0)lo=0;
            if(hi>=bins)hi=bins-1;
            for(b=lo;b<=hi;b++) curve[b]+=mag[i]*kernel[abs(b-hb)]*weights[h];
        }
    }
    return bins;
}
int PitchYinCurve(const float *mag,float *curve)
{
    int i;double sum=0,cumulative=0;
    if(!initialized)PitchInit();
    memset(imag_fft,0,sizeof(imag_fft));
    for(i=0;i<PITCH_BINS;i++) {
        float p;
        if(mag[i]<0 || !isfinite(mag[i]))return 0;
        p=mag[i]*mag[i]*yin_weight[i];
        if(!isfinite(p))return 0;
        real_fft[i]=p;if(i>0)real_fft[PITCH_N-i]=p;sum+=p;
    }
    if(sum<=0){for(i=0;i<PITCH_BINS;i++)curve[i]=1;return 0;}
    sum*=2;
    fft_forward();curve[0]=1;
    for(i=1;i<PITCH_BINS;i++) {
        double d=sum-real_fft[i];
        if(d<0)d=0; /* numerical guard for float FFT roundoff */
        cumulative+=d;curve[i]=cumulative>0?(float)(d*i/cumulative):1;
    }
    return 1;
}
static void insert_peak(float f,float m,float db)
{
    int i=npeaks,j;
    if(i==PITCH_MAX_PEAKS) {i=0;for(j=1;j<npeaks;j++)if(peak_mag[j]<peak_mag[i])i=j;if(m<=peak_mag[i])return;}
    else npeaks++;
    peak_freq[i]=f;peak_mag[i]=m;peak_db[i]=db;
}
int PitchPrepare(const float *mag,const PitchConfig *c,PitchReport *r)
{
    int k,j,low;float mx=0,median,threshold;
    memset(r,0,sizeof(*r));npeaks=0;
    blank(&r->twm,PITCH_QUIET);blank(&r->salience,PITCH_QUIET);blank(&r->yinfft,PITCH_QUIET);
    if(!isfinite(c->min_hz)||!isfinite(c->max_hz)||c->min_hz<20 || c->max_hz>5000 || c->max_hz<=c->min_hz ||
       !isfinite(c->min_peak)||c->min_peak<=0 || !isfinite(c->min_peak_median_ratio)||c->min_peak_median_ratio<1 ||
       !isfinite(c->relative_peak_db)||c->relative_peak_db<=0 || c->relative_peak_db>100 ||
       !isfinite(c->peak_floor)||c->peak_floor<0 || !isfinite(c->twm_max_error)||
       !isfinite(c->yin_min_confidence)||c->yin_min_confidence<0||c->yin_min_confidence>1 ||
       120*log2f(c->max_hz/c->min_hz)+1>=PITCH_SALIENCE_BINS) {
        r->gate_reason=PITCH_BAD_INPUT;return 0;
    }
    low=(int)floorf(c->min_hz/BIN_HZ)-1;if(low<1)low=1;
    for(k=0;k<PITCH_BINS;k++) {
        if(!isfinite(mag[k])||mag[k]<0){r->gate_reason=PITCH_BAD_INPUT;return 0;}
        if(k>=low && k<PITCH_BINS-1 && mag[k]>mx)mx=mag[k];
        if(k>0 && k<PITCH_BINS-1)sort_work[k-1]=mag[k];
    }
    qsort(sort_work,PITCH_BINS-2,sizeof(float),cmp_float);median=sort_work[(PITCH_BINS-2)/2];
    r->peak_amplitude=mx;r->median_amplitude=median;
    if(mx<c->min_peak || mx/fmaxf(median,1.0f)<c->min_peak_median_ratio){r->gate_reason=PITCH_QUIET;return 0;}
    for(k=0;k<PITCH_BINS;k++)norm_mag[k]=mag[k]/mx;
    threshold=fmaxf(c->peak_floor/mx,powf(10,-c->relative_peak_db/20));
    for(k=low;k<PITCH_BINS-1;k++) if(norm_mag[k]>threshold && norm_mag[k]>=norm_mag[k-1] && norm_mag[k]>norm_mag[k+1]) {
        float a=20*log10f(fmaxf(norm_mag[k-1],1e-10f));
        float b=20*log10f(norm_mag[k]);
        float d=20*log10f(fmaxf(norm_mag[k+1],1e-10f));
        float den=a-2*b+d,delta=fabsf(den)>1e-10f?.5f*(a-d)/den:0;
        float interpolated;
        delta=clampf(delta,-.5f,.5f);interpolated=b-.25f*(a-d)*delta;
        insert_peak((k+delta)*BIN_HZ,powf(10,interpolated/20),interpolated);
    }
    for(k=1;k<npeaks;k++)for(j=k;j>0 && peak_freq[j]<peak_freq[j-1];j--) {
        float t=peak_freq[j];peak_freq[j]=peak_freq[j-1];peak_freq[j-1]=t;
        t=peak_mag[j];peak_mag[j]=peak_mag[j-1];peak_mag[j-1]=t;
        t=peak_db[j];peak_db[j]=peak_db[j-1];peak_db[j-1]=t;
    }
    r->peak_count=npeaks;
    if(npeaks) {j=0;for(k=1;k<npeaks;k++)if(peak_mag[k]>peak_mag[j])j=k;r->dominant_hz=peak_freq[j];}
    r->gate_reason=PITCH_OK;return 1;
}
void PitchRunTwm(const PitchConfig *c,PitchResult *r)
{
    int i,h,nc=0;float error=1e30f,f;
    blank(r,PITCH_NO_ESTIMATE);
    if(npeaks<3) {
        int best=-1;for(i=0;i<npeaks;i++)if(peak_freq[i]>=c->min_hz && peak_freq[i]<=c->max_hz &&
            (best<0 || peak_mag[i]>peak_mag[best]))best=i;
        if(best>=0)finish(r,peak_freq[best],0,1,PITCH_MODE_SINGLE_PEAK);
        return;
    }
    for(i=0;i<npeaks;i++)for(h=1;h<=(c->twm_subharmonics?4:1);h++) {
        f=peak_freq[i]/h;
        if(f>=c->min_hz && f<=c->max_hz && nc<PITCH_MAX_PEAKS*4)candidates[nc++]=f;
    }
    if(!nc)return;
    qsort(candidates,nc,sizeof(float),cmp_float);
    f=PitchTwmCore(peak_freq,peak_db,npeaks,candidates,nc,&error);
    finish(r,f,error,f>0 && error<c->twm_max_error,c->twm_subharmonics?PITCH_MODE_EXTENDED:PITCH_MODE_CORE);
}
void PitchRunSalience(const PitchConfig *c,PitchResult *r)
{
    int i,best=0,n=PitchSalienceCore(peak_freq,peak_mag,npeaks,c->min_hz,c->max_hz,salience_curve);
    float second=0,delta=0,f,q;
    blank(r,PITCH_NO_ESTIMATE);if(!n)return;
    for(i=1;i<n;i++)if(salience_curve[i]>salience_curve[best])best=i;
    if(salience_curve[best]<=0)return;
    for(i=0;i<n;i++)if(abs(i-best)>10 && salience_curve[i]>second)second=salience_curve[i];
    if(best>0 && best<n-1) {
        float a=salience_curve[best-1],b=salience_curve[best],d=salience_curve[best+1],den=a-2*b+d;
        if(fabsf(den)>1e-12f)delta=clampf(.5f*(a-d)/den,-.5f,.5f);
    }
    f=c->min_hz*powf(2,(best+delta)/120.0f);
    q=clampf((salience_curve[best]-second)/salience_curve[best],0,1);
    finish(r,f,q,f>=c->min_hz && f<=c->max_hz,PITCH_MODE_CORE);
}
void PitchRunYinFFT(const PitchConfig *c,PitchResult *r)
{
    int i,lo=(int)floorf(FS_F/c->max_hz),hi=(int)ceilf(FS_F/c->min_hz),have_best=0;
    float best_tau=0,best_value=1e30f,f,q;
    blank(r,PITCH_NO_ESTIMATE);if(!PitchYinCurve(norm_mag,yin_curve))return;
    if(lo<1)lo=1;
    if(hi>PITCH_BINS-2)hi=PITCH_BINS-2;
    for(i=lo;i<=hi;i++)if(yin_curve[i]<=yin_curve[i-1] && yin_curve[i]<yin_curve[i+1]) {
        float a=yin_curve[i-1],b=yin_curve[i],d=yin_curve[i+1],den=a-2*b+d;
        float delta=0,tau,value,candidate_hz;
        /* v2: interpolate EVERY local trough before ranking. Comparing integer
         * samples first can favor a multiple of the true period merely because
         * it lies closer to an integer (captured E5 selected 4*T in v1).
         * This follows PeakDetection's interpolate-then-sort ordering. */
        if(fabsf(den)>1e-12f)delta=clampf(.5f*(a-d)/den,-.5f,.5f);
        tau=i+delta;value=b-.25f*(a-d)*delta;
        if(tau<=0 || !isfinite(tau) || !isfinite(value))continue;
        candidate_hz=FS_F/tau;
        /* floor/ceil lag bounds include edge candidates whose fitted position
         * may be outside the requested range. Filter them BEFORE selection. */
        if(candidate_hz<c->min_hz || candidate_hz>c->max_hz)continue;
        /* Ascending tau and strict comparison preserve shorter-period ties. */
        if(!have_best || value<best_value) {
            best_tau=tau;best_value=value;have_best=1;
        }
        /* Optional YIN-style first sufficiently deep trough. This is an
         * explicit policy adaptation, now using the fitted trough value too. */
        if(c->yin_first_minimum && value<=1-c->yin_min_confidence) {
            best_tau=tau;best_value=value;have_best=1;break;
        }
    }
    if(!have_best)return;
    f=FS_F/best_tau;q=clampf(1-best_value,0,1);
    finish(r,f,q,q>=c->yin_min_confidence && f>=c->min_hz && f<=c->max_hz,
           c->yin_first_minimum?PITCH_MODE_EXTENDED:PITCH_MODE_CORE);
}
void PitchAnalyze(const float *mag,const PitchConfig *c,unsigned mask,PitchReport *r)
{
    if(!PitchPrepare(mag,c,r)) {
        blank(&r->twm,r->gate_reason);blank(&r->salience,r->gate_reason);blank(&r->yinfft,r->gate_reason);return;
    }
    if(mask&PITCH_TWM)PitchRunTwm(c,&r->twm);else blank(&r->twm,PITCH_DISABLED);
    if(mask&PITCH_SALIENCE)PitchRunSalience(c,&r->salience);else blank(&r->salience,PITCH_DISABLED);
    if(mask&PITCH_YINFFT)PitchRunYinFFT(c,&r->yinfft);else blank(&r->yinfft,PITCH_DISABLED);
}
void PitchNoteName(int midi,char *out,unsigned size)
{
    static const char *name[12]={"C","C#","D","D#","E","F","F#","G","G#","A","A#","B"};
    if(!size)return;
    if(midi<0 || midi>127)snprintf(out,size,"-");
    else snprintf(out,size,"%s%d",name[midi%12],midi/12-1);
}
