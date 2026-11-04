"""Finite simple-S2MM ownership. Read completion length before arming next bank."""
import threading
import time
import numpy as np

class NoPacketYet(TimeoutError):pass
class ReceiverCancelled(RuntimeError):pass
class DMAFault(RuntimeError):pass

def controlled(method):
    def wrapped(self,*args,**kwargs):
        with self.control:return method(self,*args,**kwargs)
    return wrapped

class PacketReceiver:
    def __init__(self,mmio,allocator,words,transport_timeout=3.,clock=time.monotonic):
        self.control=threading.RLock()
        self.mmio=mmio;self.words=words;self.byte_count=words*4;self.clock=clock;self.transport_timeout=transport_timeout
        padded=((words+15)//16)*16
        self.buffers=[allocator(shape=(padded,),dtype='u4'),allocator(shape=(padded,),dtype='u4')]
        self.index=0;self.buffer=self.buffers[0];self.armed=False;self.failed=False;self.halted=False;self.closed=False
        self.cancel_event=threading.Event();self.in_receive=threading.Event();self.pending_since=None;self.startup_discards=0
        addresses=[int(b.physical_address) for b in self.buffers]
        if len(set(addresses))!=2 or any(a%64 or a+int(b.nbytes)>2**32 for a,b in zip(addresses,self.buffers)):
            raise ValueError('DMA requires two distinct 64-byte aligned 32-bit buffers')
        self.mmio.write(0x30,4);self._wait(lambda:not self.mmio.read(0x30)&4,1,'DMA reset')
        self._wait(lambda:bool(self.mmio.read(0x34)&1),1,'DMA reset halt');self.halted=True
    def _wait(self,predicate,timeout,operation):
        deadline=self.clock()+timeout
        while not predicate():
            if self.clock()>deadline:raise DMAFault(operation+' timeout')
            time.sleep(.0002)
    @controlled
    def arm(self,index=None):
        if self.closed or self.failed:raise DMAFault('DMA is closed/failed')
        if self.cancel_event.is_set():raise ReceiverCancelled('DMA stopped')
        if index is not None:self.index=index
        self.buffer=self.buffers[self.index];self.buffer.flush();self.mmio.write(0x34,0x7000)
        self.mmio.write(0x30,1)
        self._wait(lambda:not self.mmio.read(0x34)&1,1,'DMA start/halted release')
        self.halted=False;self.mmio.write(0x48,int(self.buffer.physical_address));self.mmio.write(0x4C,0)
        self.mmio.write(0x58,self.byte_count);self.pending_since=self.clock();self.armed=True
    def receive(self,timeout=.02):
        if self.closed or self.failed:raise DMAFault('DMA is closed/failed; start a new managed session')
        self.in_receive.set()
        try:
            if not self.armed:self.arm()
            call_deadline=self.clock()+timeout
            while True:
                if self.cancel_event.is_set():raise ReceiverCancelled('DMA stopped')
                status=int(self.mmio.read(0x34))
                if status&0x4770:raise DMAFault('DMA S2MM error 0x%08X'%status)
                if status&0x1000 and status&2:
                    count=int(self.mmio.read(0x58)) # Must precede the NEXT length write.
                    self.armed=False
                    if count!=self.byte_count:raise DMAFault('Short/oversized DMA packet: %d; required %d'%(count,self.byte_count))
                    finished=self.buffers[self.index]
                    self.arm(self.index^1) # Different bank; never overwrite data being copied.
                    finished.invalidate()
                    return np.array(finished[:self.words],copy=True)
                if self.clock()-self.pending_since>self.transport_timeout:raise DMAFault('DMA transport deadline: status=0x%08X'%status)
                if self.clock()>call_deadline:raise NoPacketYet('No completed packet yet')
                time.sleep(.0002)
        except (NoPacketYet,ReceiverCancelled):raise
        except Exception:
            self.failed=True;raise
        finally:self.in_receive.clear()
    def request_stop(self):self.cancel_event.set()
    cancel=request_stop
    @controlled
    def halt(self):
        if self.closed:return
        self.request_stop();self.mmio.write(0x30,0)
        try:self._wait(lambda:bool(self.mmio.read(0x34)&1),1,'DMA halt')
        except DMAFault:
            self.mmio.write(0x30,4);self._wait(lambda:not self.mmio.read(0x30)&4,1,'DMA stop/reset')
            self._wait(lambda:bool(self.mmio.read(0x34)&1),1,'DMA reset halt')
        self.armed=False;self.halted=True
    @controlled
    def release(self):
        if self.closed:return
        if not self.halted or self.in_receive.is_set():raise DMAFault('Retain buffers: DMA/CPU not quiescent')
        for b in self.buffers:b.freebuffer()
        self.closed=True
    def close(self):
        self.halt();self.release()
