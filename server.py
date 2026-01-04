<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Malwa RIS</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0">

<style>
body{font-family:Segoe UI,Arial;background:#f4f6fb;padding:20px}
.box{background:#fff;padding:20px;border-radius:12px;max-width:1200px;margin:auto}
.top-row{display:flex;gap:12px;align-items:flex-end;background:#f8fafc;padding:14px;border-radius:12px;border:1px solid #e5e7eb;flex-wrap:wrap}
.field{display:flex;flex-direction:column}
.field.small{flex:0 0 140px}
.field.medium{flex:0 0 180px}
.field.large{flex:1}
label{font-size:13px;color:#374151}
select,input{padding:8px 10px;border-radius:8px;border:1px solid #d1d5db}
button{padding:11px 14px;font-weight:600;border:none;border-radius:10px;cursor:pointer}
.btn-report{background:#2563eb;color:#fff}
.btn-template{background:#059669;color:#fff}
#content{min-height:260px;border:1px solid #d1d5db;border-radius:10px;padding:12px;background:#fff}
pre{background:#0f172a;color:#e5e7eb;padding:12px;border-radius:8px;max-height:200px;overflow:auto}
.title{text-align:center;font-size:56px;font-weight:900;letter-spacing:4px;color:#0ea5e9}
.subtitle{text-align:center;color:#64748b;margin-bottom:20px;font-weight:600}
</style>
</head>

<body>
<div class="title">MALWA RIS</div>
<div class="subtitle">Radiology Information System</div>

<div class="box">

<h3>Create / Edit Report</h3>
<div class="top-row">
  <div class="field small"><label>Modality</label><select id="reportModality"><option>CT</option><option>MRI</option><option>USG</option><option>XRAY</option></select></div>
  <div class="field large"><label>Patient Name</label><input id="patientName"></div>
  <div class="field medium"><label>Patient ID</label><input id="patientId"></div>
  <div class="field medium"><label>Date</label><input id="reportDate" type="date"></div>
</div>
<br>
<div class="top-row">
  <button onclick="cmd('bold')"><b>B</b></button>
  <button onclick="cmd('italic')"><i>I</i></button>
  <button onclick="cmd('underline')"><u>U</u></button>
  <button onclick="cmd('insertUnorderedList')">•</button>
</div>
<div id="content" contenteditable="true"></div>
<br>
<div class="top-row">
  <button class="btn-report" onclick="saveReport()">Save Report</button>
</div>

<hr>

<h3>Templates</h3>
<div class="top-row">
  <div class="field small"><label>Template Modality</label>
    <select id="templateModality" onchange="loadTemplateList()">
      <option value="">–</option>
      <option>CT</option><option>MRI</option><option>USG</option><option>XRAY</option>
    </select>
  </div>
  <div class="field large"><label>Template</label>
    <select id="templateList" onchange="loadTemplate()">
      <option value="">Select template</option>
    </select>
  </div>
  <button class="btn-template" onclick="saveTemplate()">Save Template</button>
</div>

<br>
<h4>Batch Upload Templates</h4>
<div class="top-row">
  <div class="field large"><input type="file" id="batchTemplates" multiple accept=".docx,.html"></div>
  <button class="btn-template" onclick="batchUploadTemplates()">Upload Templates</button>
</div>

<hr>

<h3>Batch Upload Reports</h3>
<div class="top-row">
  <div class="field small"><label>Modality</label><select id="uploadReportModality"><option>CT</option><option>MRI</option><option>USG</option><option>XRAY</option></select></div>
  <div class="field large"><input type="file" id="uploadReportFile" multiple accept=".docx,.html"></div>
  <button class="btn-report" onclick="batchUploadReportsDifferentPatients()">Upload</button>
</div>

<hr>

<h3>Fetch Reports</h3>
<div class="top-row">
  <div class="field small"><label>Modality</label><select id="fetchModality"><option value="">ALL</option><option>CT</option><option>MRI</option><option>USG</option><option>XRAY</option></select></div>
  <div class="field large"><label>Patient Name</label><input id="fetchName"></div>
  <div class="field medium"><label>From</label><input id="fetchDateFrom" type="date"></div>
  <div class="field medium"><label>To</label><input id="fetchDateTo" type="date"></div>
  <button class="btn-report" onclick="fetchReports()">Fetch</button>
</div>
<br>
<div id="reportList"></div>

<hr>
<pre id="result">Ready</pre>
</div>

<script>
const API = "https://malwa-ris-backend.onrender.com";

function cmd(c){document.execCommand(c,false,null)}

async function safeFetch(url, options={}){
  const res = await fetch(url, options);
  const text = await res.text();
  if(!res.ok) throw new Error(`HTTP ${res.status}: ${text.slice(0,300)}`);
  try{ return JSON.parse(text); }
  catch{ return { message: text }; }
}

function saveReport(){
  safeFetch(API+"/save_report",{
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({
      modality:reportModality.value,
      patient_name:patientName.value||"UNKNOWN",
      patient_id:patientId.value||"AUTO",
      date:reportDate.value||new Date().toISOString().slice(0,10),
      content:content.innerHTML
    })
  }).then(d=>result.textContent=JSON.stringify(d,null,2))
    .catch(e=>result.textContent=e.message);
}

function saveTemplate(){
  if(!templateModality.value){result.textContent="Select template modality";return;}
  const name = prompt("Template name?");
  if(!name) return;
  safeFetch(API+"/save_template",{
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({modality:templateModality.value,name:name,content:content.innerHTML})
  }).then(d=>result.textContent=JSON.stringify(d,null,2))
    .catch(e=>result.textContent=e.message);
}

function loadTemplateList(){
  templateList.innerHTML='<option>Loading…</option>';
  if(!templateModality.value){templateList.innerHTML='<option>Select template</option>';return;}
  safeFetch(API+"/list_templates?modality="+templateModality.value)
    .then(d=>{
      const list = Array.isArray(d.templates)?d.templates:[];
      templateList.innerHTML='<option value="">Select template</option>';
      if(!list.length){templateList.innerHTML='<option>No templates</option>';return;}
      list.forEach(t=>{const o=document.createElement('option');o.value=t;o.textContent=t;templateList.appendChild(o);});
    })
    .catch(e=>result.textContent=e.message);
}

function loadTemplate(){
  if(!templateList.value) return;
  safeFetch(API+`/load_template?modality=${templateModality.value}&filename=${encodeURIComponent(templateList.value)}`)
    .then(d=>content.innerHTML=d.content||"")
    .catch(e=>result.textContent=e.message);
}

function batchUploadTemplates(){
  if(!templateModality.value){result.textContent="Select template modality";return;}
  const fd=new FormData();fd.append("modality",templateModality.value);
  for(const f of batchTemplates.files) fd.append("files",f);
  safeFetch(API+"/batch_upload_templates",{method:"POST",body:fd})
    .then(d=>result.textContent=JSON.stringify(d,null,2))
    .catch(e=>result.textContent=e.message);
}

function batchUploadReportsDifferentPatients(){
  const fd=new FormData();fd.append("modality",uploadReportModality.value);
  for(const f of uploadReportFile.files) fd.append("files",f);
  safeFetch(API+"/batch_upload_reports_auto",{method:"POST",body:fd})
    .then(d=>result.textContent=JSON.stringify(d,null,2))
    .catch(e=>result.textContent=e.message);
}

function fetchReports(){
  reportList.innerHTML="Loading…";
  const p=new URLSearchParams();
  if(fetchModality.value) p.append("modality",fetchModality.value);
  if(fetchName.value) p.append("name",fetchName.value);
  if(fetchDateFrom.value) p.append("from",fetchDateFrom.value);
  if(fetchDateTo.value) p.append("to",fetchDateTo.value);
  safeFetch(API+"/list_reports?"+p.toString())
    .then(d=>{
      reportList.innerHTML="";
      (d.reports||[]).forEach(r=>{
        const div=document.createElement('div');div.className='top-row';div.style.marginBottom='8px';
        div.innerHTML=`<div class=\"field large\"><b>${r.filename}</b><br>${r.path}</div>
        <button onclick=\"downloadReport('${r.path}','docx')\">Word</button>
        <button onclick=\"downloadReport('${r.path}','pdf')\">PDF</button>`;
        reportList.appendChild(div);
      });
      result.textContent=JSON.stringify(d,null,2);
    })
    .catch(e=>result.textContent=e.message);
}

function downloadReport(path,type){window.open(API+`/download_report?path=${encodeURIComponent(path)}&type=${type}`,'_blank');}
</script>
</body>
</html>





