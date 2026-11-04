"""Dependency-injected ONE-PACKET AXI DMA simple-S2MM bring-up template.
No address, board, payload, overlay or producer is selected here.
Caller owns producer_start/stop; inspect this template before adapting it.
"""
import time

class UnsafeStop(RuntimeError):pass
class SimpleS2MMSession:
    def __init__(self,mmio,allocate,n_words,producer_start,producer_stop,timeout=1.,address_alignment=4):
        if n_words<=0 or timeout<=0:raise ValueError('positive packet length and timeout required')
        self.mmio,self.allocate=mmio,allocate;self.n_words=n_words
        self.producer_start,self.producer_stop=producer_start,producer_stop
        self.timeout=timeout;self.address_alignment=address_alignment
        self.buffer=None;self.state='NEW'
    def _wait(self,predicate):
        deadline=time.monotonic()+self.timeout
        while not predicate():
            if time.monotonic()>=deadline:raise TimeoutError('DMA deadline')
            time.sleep(.0001)
    def arm(self):
        if self.state!='NEW':raise RuntimeError('one owner, one arm per bring-up session')
        if self.mmio.read(0x34)&8:raise ValueError('scatter-gather DMA requires a different adapter')
        self.buffer=self.allocate(shape=(self.n_words,),dtype='u4');self.state='ALLOCATED'
        try:
            address=int(self.buffer.physical_address)
            if address%self.address_alignment:raise ValueError('buffer address alignment mismatch')
            self.mmio.write(0x30,4);self._wait(lambda:not(self.mmio.read(0x30)&4))
            self.mmio.write(0x34,0x7000);self.mmio.write(0x30,1)
            self.mmio.write(0x48,address&0xffffffff);self.mmio.write(0x4c,address>>32)
            self.buffer.flush();self.mmio.write(0x58,self.n_words*4)
            self.state='ARMED';self.producer_start();self.state='RUNNING'
        except Exception:
            self.state='QUARANTINED';raise
    def receive_copy(self):
        if self.state!='RUNNING':raise RuntimeError('not running')
        def complete():
            status=self.mmio.read(0x34)
            if status&0x4770:raise RuntimeError('DMA status error: '+hex(status))
            return bool(status&2 and status&0x1000)
        self._wait(complete)
        if int(self.mmio.read(0x58))!=self.n_words*4:raise ValueError('actual BTT differs from fixed packet contract')
        self.buffer.invalidate()
        return self.buffer.copy()
    def close(self):
        if self.state=='CLOSED':return
        if self.buffer is None:self.state='CLOSED';return
        try:
            self.producer_stop()
            self.mmio.write(0x30,self.mmio.read(0x30)&~1)
            self._wait(lambda:bool(self.mmio.read(0x34)&1))
        except Exception as exc:
            self.state='QUARANTINED'
            raise UnsafeStop('producer/DMA stop unconfirmed; retain buffer and owner') from exc
        self.buffer.freebuffer();self.buffer=None;self.state='CLOSED'
