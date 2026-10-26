// Photo switcher of one model card (MODEL-GALLERY-001): the left and right halves of the photo are
// buttons with yellow arrows; each shows the previous or next photo, wrapping around.
export function gallery(photos, {base, alt, labels, lazy}) {
  const box=document.createElement('div');
  box.className='gallery';
  box.setAttribute('role','group');
  box.setAttribute('aria-roledescription',labels.gallery);
  box.setAttribute('aria-label',alt);
  const img=document.createElement('img');
  img.decoding='async';img.loading=lazy?'lazy':'eager';
  let index=0;
  const url=i=>new URL(photos[i].path,base);
  function show(next) {
    index=(next+photos.length)%photos.length;
    const photo=photos[index];
    img.src=url(index);img.width=photo.width;img.height=photo.height;
    img.alt=`${alt} — ${index+1}/${photos.length}`;
  }
  show(0);
  box.append(img);
  if(photos.length<2) return box;
  for(const [step,side,label] of [[-1,'prev',labels.prev],[1,'next',labels.next]]) {
    const button=document.createElement('button');
    button.type='button';button.className=`gallery-${side}`;button.setAttribute('aria-label',label);
    button.addEventListener('click',()=>{
      show(index+step);
      new Image().src=url((index+step+photos.length)%photos.length);
    });
    box.append(button);
  }
  return box;
}
