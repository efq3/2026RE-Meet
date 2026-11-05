"use strict";
const colors = ["#ff6b6b", "#4ecdc4", "#ffd166", "#7aa2ff"];
const labels = {data_missing:"데이터 없음", warming_up:"계산 구간 수집 중", context_missing:"비행 정보 부족 · 진동 판정 보류", disarmed:"외부 입력 DISARMED · 진동 판정 보류", maneuver:"기동 중 · 진동 판정 보류", observing:"관찰 중 · 검증 전", vibration_candidate:"진동 증가 후보", thermal_candidate:"온도 이상 후보", compound_candidate:"복합 이상 후보"};
const byId = id => document.getElementById(id);
const fmt = (v, digits=2) => typeof v === "number" && Number.isFinite(v) ? v.toFixed(digits) : "—";
let history = [];
let lastPackets = -1;
let lastEvent = 0;
let latest = null;
const cards = colors.map((color, i) => {
  const el = document.createElement("article");
  el.className = "arm";
  el.style.setProperty("--color", color);
  el.innerHTML = `<h2>Arm ${i+1}</h2><div class="reading"></div><p class="rms"></p><p class="relative"></p><p class="rate"></p><p class="status"></p><p class="tempAge"></p>`;
  byId("arms").append(el);
  return el;
});
function plot(id, key) {
  const canvas = byId(id);
  const rect = canvas.getBoundingClientRect();
  const dpr = devicePixelRatio || 1;
  canvas.width = Math.round(rect.width*dpr); canvas.height = Math.round(rect.height*dpr);
  const ctx = canvas.getContext("2d");ctx.scale(dpr,dpr);
  const w=rect.width,h=rect.height,left=48,right=w-12,top=12,bottom=h-30;
  const values=history.flatMap(p=>p.arms.map(a=>a[key])).filter(v=>typeof v==="number"&&Number.isFinite(v));
  let lo=key==="rms"?0:(values.length?Math.min(...values)-1:0);
  let hi;
  if(key==="rms"){
    const peak=values.length?Math.max(...values):0;
    // Keep normal 0.01-0.03 m/s^2 quantization noise from filling the plot.
    // Expand only when a physically meaningful RMS increase exceeds the base scale.
    hi=Math.max(0.25,Math.ceil((peak*1.15)/0.05)*0.05);
  }else{
    hi=values.length?Math.max(...values)+1:1;
  }
  if(hi<=lo)hi=lo+1;
  ctx.font="11px Segoe UI";ctx.lineWidth=1;
  for(let k=0;k<=4;k++){
    const y=top+(bottom-top)*k/4;ctx.strokeStyle="#2c405c";ctx.beginPath();ctx.moveTo(left,y);ctx.lineTo(right,y);ctx.stroke();
    ctx.fillStyle="#9fb0d0";ctx.fillText((hi-(hi-lo)*k/4).toFixed(2),2,y+4);
  }
  if(!history.length){ctx.fillText("Waiting for telemetry",left+15,top+30);return;}
  const start=history[0].received_unix,end=Math.max(start+1,history.at(-1).received_unix);
  colors.forEach((color,i)=>{
    ctx.strokeStyle=color;ctx.lineWidth=1.8;ctx.beginPath();let active=false;
    for(const p of history){const v=p.arms[i][key];if(v===null){active=false;continue;}
      const x=left+(p.received_unix-start)/(end-start)*(right-left),y=bottom-(v-lo)/(hi-lo)*(bottom-top);
      if(active)ctx.lineTo(x,y);else ctx.moveTo(x,y);active=true;
    }ctx.stroke();
  });
  ctx.fillStyle="#9fb0d0";ctx.fillText(new Date(start*1000).toLocaleTimeString(),left,h-8);
  ctx.textAlign="right";ctx.fillText(new Date(end*1000).toLocaleTimeString(),right,h-8);
}
function render(data){
  latest=data; lastEvent=Date.now();
  const live=data.last_packet_age_s!==null&&data.last_packet_age_s<3;
  const px4Gazebo=data.simulation&&data.flight_context_source==="px4-gazebo-sitl";
  byId("connection").textContent=live?(px4Gazebo?"LIVE · PX4 GAZEBO":data.simulation?"LIVE · DEMO":data.replay?"LIVE · REPLAY":"LIVE"):"수신 대기 / 데이터 오래됨";
  byId("counter").textContent=`${data.packets} packets`;
  const fc=data.flight_context;
  const armText=fc.armed===true?"ARMED":fc.armed===false?"DISARMED":"상태 불명";
  const contextSource=data.flight_context_source?`${data.flight_context_source}${data.simulation?" (SIM)":""} 입력`:data.simulation?"SIM 입력":"외부 입력";
  byId("flight").textContent=`${contextSource}: ${armText} / ${fc.flight_mode||"모드 없음"}`;
  byId("baselineState").textContent=data.baseline_set?"시작 온도 설정됨":"미설정";
  const candidate=data.arms.filter(a=>a.thermal_candidate||a.vibration_candidate);
  const lowRate=data.arms.some(a=>a.ready&&!a.bandwidth_sufficient);
  const simulation=data.simulation;
  byId("notice").textContent=data.log_error?`로그 저장 실패: ${data.log_error}`:!live?"수신 데이터를 기다리는 중입니다. 송신 대상 노트북 IP와 TCP 포트를 확인하십시오.":candidate.length?`${candidate.map(a=>`Arm ${a.arm}`).join(", ")} 이상 후보를 확인하십시오. 원인은 별도 검증이 필요합니다.`:simulation?"가상 시험 데이터 수신 중입니다. 실기체 측정 결과가 아닙니다.":lowRate?"저속 데이터 수신 중: 고주파 모터 진동은 판단할 수 없습니다. RMS는 관측된 저주파 움직임으로 해석하십시오.":"데이터 수신 중입니다. 표시 지표와 이상 후보를 확인하십시오.";
  data.arms.forEach((a,i)=>{
    const el=cards[i];el.classList.toggle("alert",a.thermal_candidate||a.vibration_candidate);
    el.querySelector("h2").textContent=a.imu_channel
      ? `Arm ${a.arm} / IMU ${a.imu_number} (${a.imu_channel})`
      : `Arm ${a.arm}`;
    el.querySelector(".reading").textContent=`${fmt(a.temperature,1)} °C`;
    el.querySelector(".rms").textContent=`RMS ${fmt(a.rms,3)} m/s²`;
    el.querySelector(".relative").textContent=`상대 RMS ${fmt(a.relative_rms,3)} / 상대 ΔT ${fmt(a.relative_temperature,1)} °C`;
    el.querySelector(".rate").textContent=`수집 ${fmt(a.hz,1)} Hz · 나이퀴스트 ${fmt(a.nyquist_hz,1)} Hz${a.gap?" · 구간 누락":""}`;
    el.querySelector(".status").textContent=labels[a.status]||a.status;
    el.querySelector(".tempAge").textContent=a.temperature_age_known?"온도 측정시각 제공됨":"온도 측정시각 미제공 · 갱신 여부 불명";
  });
  if(data.packets!==lastPackets){
    if(data.packets<lastPackets)history=[];
    history.push(data);history=history.filter(p=>data.received_unix-p.received_unix<120).slice(-600);
    lastPackets=data.packets;
  }
  byId("quality").textContent=JSON.stringify({input_ssh:data.ssh_status,metric:data.metric,imu_channels_by_arm:data.imu_channels_by_arm,configured_imu_channels_by_arm:data.configured_imu_channels_by_arm,context_fresh:data.context_fresh,maneuver_known:data.maneuver_known,invalid_lines:data.invalid_lines,invalid_samples:data.invalid_samples,timestamp_errors:data.timestamp_errors,sequence_gaps:data.sequence_gaps,stream_conflicts:data.stream_conflicts,sources:data.sources},null,2);
  byId("logPath").textContent=`수신 원본 저장 위치: ${data.raw_log}`;
  plot("temperatureChart","temperature");plot("rmsChart","rms");
}
async function action(path){
  try{const response=await fetch(path,{method:"POST"});const result=await response.json();if(!response.ok)throw Error(result.error);if(path.endsWith("reset")){history=[];lastPackets=-1;}}
  catch(error){byId("notice").textContent=error.message;}
}
byId("baseline").onclick=()=>action("/api/baseline");
byId("reset").onclick=()=>action("/api/reset");
const events=new EventSource("/events");events.onmessage=e=>render(JSON.parse(e.data));
events.onerror=()=>{byId("connection").textContent="브라우저 재연결 중";};
setInterval(()=>{if(lastEvent&&Date.now()-lastEvent>3000)byId("connection").textContent="서버 연결 끊김";},1000);
window.addEventListener("resize",()=>{if(latest){plot("temperatureChart","temperature");plot("rmsChart","rms");}});
plot("temperatureChart","temperature");plot("rmsChart","rms");
