import React, {useEffect, useId, useState} from 'react';
import {MapPin, Building2, Link2, Search, LoaderCircle, Check, ArrowUpRight} from 'lucide-react';

function Autocomplete({label,placeholder,value,onChange,onSelect,endpoint,city='',kind,disabled}) {
 const id=useId();
 const [items,setItems]=useState([]),[busy,setBusy]=useState(false),[error,setError]=useState(''),[open,setOpen]=useState(false),[active,setActive]=useState(-1),[finished,setFinished]=useState(false);
 useEffect(()=>{
  setItems([]);setActive(-1);setError('');setFinished(false);setBusy(false);
  if(value.trim().length<2||disabled||!open)return;
  const controller=new AbortController();
  const timer=setTimeout(async()=>{
   setBusy(true);
   try{
    const params=new URLSearchParams({q:value.trim()});if(city)params.set('city',city);
    const res=await fetch(`${endpoint}?${params}`,{signal:controller.signal});
    const data=await res.json();if(!res.ok)throw new Error(data.detail||'Suggestions unavailable. You can still type a place manually.');
    if(!controller.signal.aborted){setItems(data.items||[]);setFinished(true);}
   }catch(e){if(e.name!=='AbortError'&&!controller.signal.aborted){setError('Suggestions are temporarily unavailable. You can still enter a name manually.');setFinished(true);}}
   finally{if(!controller.signal.aborted)setBusy(false);}
  },300);
  return()=>{clearTimeout(timer);controller.abort();};
 },[value,city,endpoint,disabled,open]);
 function choose(item){onSelect(item);setOpen(false);setActive(-1);}
 function keyDown(e){
  if(e.key==='Escape'){setOpen(false);return;}
  if(e.key==='ArrowDown'||e.key==='ArrowUp'){
   e.preventDefault();setOpen(true);setActive(i=>items.length?Math.max(0,Math.min(items.length-1,i+(e.key==='ArrowDown'?1:-1))):-1);
  }
  if(e.key==='Enter'&&open&&active>=0&&items[active]){e.preventDefault();choose(items[active]);}
 }
 return <div className={`autocomplete-field ${kind}`}>
  <label htmlFor={id}>{label}</label>
  <div className="autocomplete-input">{kind==='city'?<Building2 size={18}/>:<MapPin size={18}/>}<input id={id} role="combobox" aria-autocomplete="list" aria-expanded={open&&value.trim().length>=2} aria-controls={`${id}-list`} aria-activedescendant={open&&active>=0?`${id}-${active}`:undefined} value={value} placeholder={placeholder} onChange={e=>{onChange(e.target.value);setOpen(true);}} onFocus={()=>setOpen(true)} onBlur={()=>setOpen(false)} onKeyDown={keyDown} autoComplete="off" disabled={disabled}/>{busy&&<LoaderCircle size={15} className="spin"/>}</div>
  {open&&value.trim().length>=2&&<div className="suggestion-popover">
   <div className="suggestion-heading">{kind==='city'?'CITIES & AREAS':'PLACES NEAR YOUR SEARCH'}{busy&&<span>Searching…</span>}</div>
   <div id={`${id}-list`} role="listbox" aria-label={`${label} suggestions`}>
    {items.map((item,i)=>{const text=typeof item==='string'?item:item.display_name;return <button type="button" role="option" aria-selected={active===i} id={`${id}-${i}`} key={text} className={active===i?'highlighted':''} onMouseEnter={()=>setActive(i)} onMouseDown={e=>e.preventDefault()} onClick={()=>choose(item)}><MapPin size={15}/><span>{text}</span><ArrowUpRight size={13}/></button>;})}
   </div>
   <div className="suggestion-status" role="status">{error||(busy?'Finding matches with Photon…':finished&&!items.length?'No matches. Try a more specific name, or continue with your own text.':'↑ ↓ to browse · Enter to select · Esc to close')}</div>
   <div className="photon-credit">Search powered by Photon · OpenStreetMap</div>
  </div>}
 </div>;
}
export default function LocationSearch({onChange,disabled}){
 const [city,setCity]=useState(''),[place,setPlace]=useState(''),[selected,setSelected]=useState(false),[url,setUrl]=useState(''),[byUrl,setByUrl]=useState(false);
 function updateCity(value){setCity(value);setPlace('');setSelected(false);onChange('');}
 function updatePlace(value){setPlace(value);setSelected(false);onChange(value.trim()?`${value}${city?`, ${city}`:''}`:'');}
 return <div className="location-search">
  <div className="search-type-tabs"><button type="button" disabled={disabled} className={!byUrl?'active':''} onClick={()=>{setByUrl(false);onChange(place?`${place}${!selected&&city?`, ${city}`:''}`:'');}}><Search size={13}/>Search by name</button><button type="button" disabled={disabled} className={byUrl?'active':''} onClick={()=>{setByUrl(true);onChange(url);}}><Link2 size={13}/>Paste Maps link</button></div>
  {byUrl?<div className="autocomplete-field"><label htmlFor="maps-link">GOOGLE MAPS URL</label><div className="autocomplete-input"><Link2 size={18}/><input id="maps-link" type="url" placeholder="https://maps.app.goo.gl/…" value={url} onChange={e=>{setUrl(e.target.value);onChange(e.target.value);}} disabled={disabled} required/></div></div>:<div className="location-search-fields">
   <Autocomplete label="CITY / AREA" placeholder="Start with a city…" value={city} onChange={updateCity} onSelect={updateCity} endpoint="/api/suggestions/cities" kind="city" disabled={disabled}/>
   <Autocomplete label="PLACE / BUSINESS" placeholder="Café, hotel, restaurant…" value={place} onChange={updatePlace} onSelect={item=>{setPlace(item.search_name);setSelected(true);onChange(item.search_name);}} endpoint="/api/suggestions/places" city={city} kind="place" disabled={disabled}/>
  </div>}
  {selected&&!byUrl&&<div className="selection-confirmation"><Check size={12}/>Place selected · check the resolved business in your report</div>}
 </div>;
}
