import { chromium, request } from "playwright";
import fs from "node:fs";
import path from "node:path";

const FRONT = "https://tmi-music-app.onrender.com";
const API = "https://tmi-audioid-api.onrender.com";
const OUT = "evidence/live-ui";
fs.mkdirSync(OUT,{recursive:true});

const email = `capture-${Date.now()}@example.com`;
const password = "CaptureOnly2026!";
const publicApi = await request.newContext({baseURL:API});
let reg;
for (let i=0;i<12;i++) {
  try {
    const r=await publicApi.post("/api/v1/auth/register",{data:{display_name:"TMI Thesis Capture",email,password},timeout:120000});
    if(r.ok()){reg=await r.json();break;}
    console.log("register",r.status(),await r.text());
  } catch(e){ console.log("register retry",String(e)); }
  await new Promise(r=>setTimeout(r,10000));
}
if(!reg?.token) throw new Error("Could not register capture account");
const token=reg.token;
const authApi=await request.newContext({baseURL:API,extraHTTPHeaders:{Authorization:`Bearer ${token}`}});

const browser=await chromium.launch({headless:true});
const context=await browser.newContext({viewport:{width:1600,height:1000},deviceScaleFactor:1});
await context.addInitScript(({token})=>{
  localStorage.setItem("tmi_token",token);
  localStorage.setItem("tmi_lang","vi");
  localStorage.setItem("tmi_theme","dark");
},{token});
const page=await context.newPage();

async function gotoScreen(screen){
  const u = screen==="home" ? FRONT+"/" : FRONT+`/?screen=${screen}`;
  await page.goto(u,{waitUntil:"domcontentloaded",timeout:120000});
  await page.waitForTimeout(3500);
}
async function snap(name){
  await page.screenshot({path:path.join(OUT,name),fullPage:true});
}

await gotoScreen("home");
await snap("01_identify_live.png");

await gotoScreen("mine");
const add=page.getByRole("button",{name:/Thêm bài hát/i}).first();
if(await add.isVisible().catch(()=>false)) await add.click();
await page.waitForTimeout(800);
await snap("02_add_reference_live.png");

// Create one REAL private ingestion job so Activity is not a fabricated state.
const wav=fs.readFileSync("/tmp/tmi_capture.wav");
const ingest=await authApi.post("/api/v1/references/file",{multipart:{
  title:"TMI Capture Reference",
  artist:"TMI Thesis Evidence",
  scope:"private",
  file:{name:"tmi_capture.wav",mimeType:"audio/wav",buffer:wav}
},timeout:120000});
console.log("ingest status",ingest.status(),await ingest.text());
let ingestJob=null;
try { ingestJob=JSON.parse(await (await authApi.get("/api/v1/jobs")).text())?.[0]; } catch {}
if(ingestJob?.id){
  for(let i=0;i<90;i++){
    const jr=await authApi.get(`/api/v1/jobs/${ingestJob.id}`,{timeout:120000});
    const j=await jr.json();
    console.log("ingest",j.status,j.stage,j.progress);
    if(j.status==="completed"||j.status==="failed") break;
    await new Promise(r=>setTimeout(r,2000));
  }
}
await gotoScreen("activity");
await snap("03_activity_live.png");

await gotoScreen("lab");
await snap("04_model_lab_live.png");

// Identify the same real file through the UI, using PRIVATE scope.
await gotoScreen("home");
const privateBtn=page.getByRole("button",{name:/Dùng bộ nhận diện của tôi/i}).first();
if(await privateBtn.isVisible().catch(()=>false)) await privateBtn.click();
const fileInput=page.locator('label.dropZone input[type="file"]').first();
await fileInput.setInputFiles("/tmp/tmi_capture.wav");
try {
  await page.waitForFunction(()=>location.search.includes("screen=result")||location.search.includes("screen=unknown")||location.search.includes("screen=scanResult"),null,{timeout:240000});
} catch(e) { console.log("result wait",String(e)); }
await page.waitForTimeout(1500);
await snap("05_result_live.png");

await browser.close();
await publicApi.dispose();
await authApi.dispose();
console.log("CAPTURE_DONE");