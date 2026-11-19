const input=document.getElementById('videoInput'), drop=document.getElementById('dropzone'), fileRow=document.getElementById('fileRow'), fileName=document.getElementById('fileName'), fileMeta=document.getElementById('fileMeta'), createBtn=document.getElementById('createBtn'), toast=document.getElementById('toast');
let selectedFile=null, aspect='9:16';
function notify(msg){toast.textContent=msg;toast.classList.add('show');setTimeout(()=>toast.classList.remove('show'),2800)}
function setFile(file){
 if(!file)return;
 if(!file.type.startsWith('video/')){notify('Please choose a video file.');return}
 selectedFile=file;fileName.textContent=file.name;fileMeta.textContent=(file.size/1024/1024).toFixed(1)+' MB · Ready to process';
 fileRow.classList.remove('hidden');drop.classList.add('hidden');createBtn.disabled=false;
}
input.addEventListener('change',e=>setFile(e.target.files[0]));
document.getElementById('removeFile').onclick=()=>{selectedFile=null;input.value='';fileRow.classList.add('hidden');drop.classList.remove('hidden');createBtn.disabled=true};
['dragenter','dragover'].forEach(ev=>drop.addEventListener(ev,e=>{e.preventDefault();drop.classList.add('drag')}));
['dragleave','drop'].forEach(ev=>drop.addEventListener(ev,e=>{e.preventDefault();drop.classList.remove('drag')}));
drop.addEventListener('drop',e=>setFile(e.dataTransfer.files[0]));
document.querySelectorAll('.format').forEach(btn=>btn.addEventListener('click',()=>{document.querySelectorAll('.format').forEach(x=>x.classList.remove('selected'));btn.classList.add('selected');aspect=btn.dataset.aspect}));
createBtn.addEventListener('click',async()=>{
 if(!selectedFile)return;
 const form=new FormData();form.append('video',selectedFile);form.append('clip_count',document.getElementById('clipCount').value);form.append('clip_seconds',document.getElementById('clipLength').value);form.append('aspect',aspect);
 createBtn.disabled=true;document.getElementById('emptyState').classList.add('hidden');document.getElementById('results').classList.add('hidden');document.getElementById('loadingState').classList.remove('hidden');
 try{
  const res=await fetch('/api/process',{method:'POST',body:form});const data=await res.json();
  if(!res.ok)throw new Error(data.detail||'Could not process this video.');
  const results=document.getElementById('results');results.innerHTML='';
  data.clips.forEach((clip,i)=>{
   const card=document.createElement('div');card.className='clip-card';
   const thumb=document.createElement('div');thumb.className='clip-thumb';thumb.textContent='▶';
   const info=document.createElement('div');const title=document.createElement('b');title.textContent='Clip '+(i+1);const meta=document.createElement('small');meta.textContent='Starts at '+clip.start+'s · '+clip.duration+'s'+(clip.score?' · Highlight score '+clip.score:'');info.append(title,meta);
   if(clip.snippet && clip.snippet!=='Sample segment'){const quote=document.createElement('small');quote.style.display='block';quote.style.marginTop='4px';quote.textContent='“'+clip.snippet+'”';info.append(quote);}
   const link=document.createElement('a');link.className='download';link.href=clip.url;link.download=clip.name;link.textContent='↓ Download';
   card.append(thumb,info,link);results.append(card);
  });
  const note=document.createElement('p');note.className='fineprint';note.textContent=data.ai_highlights?'Speech-aware AI selected these moments. '+data.ai_note:'Fallback sample segments used. '+data.ai_note;results.append(note);
  document.getElementById('loadingState').classList.add('hidden');results.classList.remove('hidden');notify('Your clips are ready!');
 }catch(err){document.getElementById('loadingState').classList.add('hidden');document.getElementById('emptyState').classList.remove('hidden');notify(err.message)}
 finally{createBtn.disabled=!selectedFile}
});
