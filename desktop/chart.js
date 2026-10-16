(function(root){
  'use strict';
  const number = value => {
    if((typeof value !== 'number' && typeof value !== 'string') || value === '' || !Number.isFinite(Number(value))) throw Error('K 线包含无效数值');
    return Number(value);
  };
  function normalize(items){
    if(!Array.isArray(items)) throw Error('K 线数据格式错误');
    const rows=items.map(item=>{
      if(!item || typeof item !== 'object') throw Error('K 线数据格式错误');
      const row=Object.fromEntries(['time','open','high','low','close','volume'].map(key=>[key,number(item[key])]));
      if(row.time>=1e12) row.time/=1000;
      if(row.time<=0 || row.low<=0 || row.volume<0 || row.high<Math.max(row.open,row.close,row.low) || row.low>Math.min(row.open,row.close)) throw Error('K 线价格范围无效');
      return row;
    }).sort((a,b)=>a.time-b.time);
    if(rows.some((row,i)=>i && row.time===rows[i-1].time)) throw Error('K 线时间重复');
    return rows;
  }
  function bounds(rows){
    if(!rows.length)return null;
    const low=Math.min(...rows.map(r=>r.low)),high=Math.max(...rows.map(r=>r.high));
    const padding=Math.max((high-low)*0.12,high*0.0001,1e-10);
    return {min:low-padding,max:high+padding,volume:Math.max(1,...rows.map(r=>r.volume))};
  }
  function visible(rows,count,offset){
    const end=Math.max(1,rows.length-Math.max(0,Math.min(offset,rows.length-1)));
    return rows.slice(Math.max(0,end-Math.max(1,count)),end);
  }
  const price = value=>value.toLocaleString('en-US',{maximumFractionDigits:8});
  class CandleChart {
    constructor(canvas,onHover){
      this.canvas=canvas;this.ctx=canvas.getContext('2d');this.rows=[];this.count=80;this.offset=0;this.pointer=null;this.message='从左侧选择自选品种';this.onHover=onHover;
      this.observer=new ResizeObserver(()=>this.draw());this.observer.observe(canvas);
      canvas.addEventListener('mousemove',event=>{const box=canvas.getBoundingClientRect();this.pointer={x:event.clientX-box.left,y:event.clientY-box.top};this.draw();});
      canvas.addEventListener('mouseleave',()=>{this.pointer=null;this.draw();});
      canvas.addEventListener('wheel',event=>{
        if(!this.rows.length)return;
        event.preventDefault();
        if(event.shiftKey)this.offset=Math.max(0,Math.min(this.rows.length-1,this.offset+(event.deltaY>0?5:-5)));
        else this.count=Math.max(8,Math.min(500,Math.round(this.count*(event.deltaY>0?1.2:0.8))));
        this.draw();
      },{passive:false});
    }
    setData(items){
      this.rows=[];
      try{this.rows=normalize(items);this.message=this.rows.length?'':'交易所未返回该周期 K 线';}
      catch(error){this.message=error.message;this.draw();throw error;}
      this.offset=Math.min(this.offset,Math.max(0,this.rows.length-1));this.draw();
    }
    clear(message){this.rows=[];this.message=message;this.offset=0;this.pointer=null;this.draw();}
    reset(){this.count=80;this.offset=0;this.pointer=null;this.draw();}
    draw(){
      const canvas=this.canvas,ctx=this.ctx,w=canvas.clientWidth,h=canvas.clientHeight;
      if(!w||!h)return;
      const ratio=globalThis.devicePixelRatio||1;
      canvas.width=Math.round(w*ratio);canvas.height=Math.round(h*ratio);ctx.setTransform(ratio,0,0,ratio,0,0);
      ctx.fillStyle='#181818';ctx.fillRect(0,0,w,h);ctx.font='12px "Microsoft YaHei UI", "Segoe UI", sans-serif';
      const right=w-90,top=22,bottom=h-32,priceBottom=top+(bottom-top)*0.74,volTop=priceBottom+22;
      const rows=visible(this.rows,this.count,this.offset),scale=bounds(rows);
      ctx.strokeStyle='#242424';ctx.lineWidth=1;
      for(let i=0;i<=5;i++){
        const y=top+(priceBottom-top)*i/5;
        ctx.beginPath();ctx.moveTo(0,y+.5);ctx.lineTo(w,y+.5);ctx.stroke();
        if(scale){ctx.fillStyle='#748398';ctx.fillText(price(scale.max-(scale.max-scale.min)*i/5),right+10,y+4);}
      }
      for(let i=1;i<=5;i++){const x=right*i/5;ctx.beginPath();ctx.moveTo(x,.5);ctx.lineTo(x,bottom);ctx.stroke();}
      ctx.fillStyle='#748398';ctx.fillText('VOLUME',12,volTop+10);
      if(!scale){ctx.textAlign='center';ctx.font='13px system-ui';ctx.fillStyle='#8d9bb0';ctx.fillText(this.message,right/2,h/2);ctx.textAlign='left';this.onHover?.(null);return;}
      const step=right/Math.max(8,rows.length),bar=Math.max(1,Math.min(15,step*.68));
      const y=value=>top+(scale.max-value)/(scale.max-scale.min)*(priceBottom-top);
      rows.forEach((row,index)=>{
        const x=step*(index+.5),color=row.close>=row.open?'#29c7a2':'#ef6674';
        ctx.strokeStyle=color;ctx.fillStyle=color;ctx.beginPath();ctx.moveTo(x,y(row.high));ctx.lineTo(x,y(row.low));ctx.stroke();
        ctx.fillRect(x-bar/2,Math.min(y(row.open),y(row.close)),bar,Math.max(1,Math.abs(y(row.close)-y(row.open))));
        ctx.globalAlpha=.48;const vh=(bottom-volTop-15)*row.volume/scale.volume;ctx.fillRect(x-bar/2,bottom-vh,bar,vh);ctx.globalAlpha=1;
      });
      for(let i=0;i<4;i++){
        const index=Math.min(rows.length-1,Math.floor(i*rows.length/4)),row=rows[index];
        ctx.fillStyle='#748398';ctx.fillText(new Date(row.time*1000).toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}),Math.max(4,step*(index+.5)-30),h-10);
      }
      const latest=rows[rows.length-1];
      ctx.setLineDash([4,4]);ctx.strokeStyle=latest.close>=latest.open?'#29c7a277':'#ef667477';ctx.beginPath();ctx.moveTo(0,y(latest.close));ctx.lineTo(right,y(latest.close));ctx.stroke();ctx.setLineDash([]);
      let selected=latest;
      if(this.pointer && this.pointer.x>=0 && this.pointer.x<right && this.pointer.y>=top && this.pointer.y<bottom){
        const index=Math.min(rows.length-1,Math.max(0,Math.floor(this.pointer.x/step)));selected=rows[index];const x=step*(index+.5);
        ctx.strokeStyle='#a3afc0';ctx.setLineDash([3,4]);ctx.beginPath();ctx.moveTo(x,top);ctx.lineTo(x,bottom);ctx.moveTo(0,this.pointer.y);ctx.lineTo(right,this.pointer.y);ctx.stroke();ctx.setLineDash([]);
        if(this.pointer.y<=priceBottom){ctx.fillStyle='#27384c';ctx.fillRect(right,this.pointer.y-10,90,20);ctx.fillStyle='#e0e8f4';ctx.fillText(price(scale.max-(this.pointer.y-top)/(priceBottom-top)*(scale.max-scale.min)),right+7,this.pointer.y+4);}
      }
      this.onHover?.(selected);
    }
  }
  const api={normalize,bounds,visible,CandleChart};
  if(typeof module!=='undefined' && module.exports)module.exports=api;else root.MarketChart=api;
})(globalThis);
