import json, os
from pathlib import Path
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser=p.chromium.launch()
    page=browser.new_page(viewport={'width':1440,'height':1150})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(os.environ.get('NEWS_MAP_URL', 'http://127.0.0.1:8766/docs/index.html#overview'))
    page.locator('#topic-map').scroll_into_view_if_needed()
    page.screenshot(path='.audit/map-wide.png')
    assert page.locator('.news-cluster').count()==11
    assert page.locator('.map-story').count()>11
    page.locator('#map-categories button[data-category=economy]').click()
    page.locator('#topic-map').scroll_into_view_if_needed()
    page.screenshot(path='.audit/map-close.png')
    before=page.locator('#topic-map').get_attribute('data-camera')
    scroll_before=page.evaluate('({x:scrollX,y:scrollY,left:document.getElementById("topic-map").scrollLeft,top:document.getElementById("topic-map").scrollTop})')
    page.locator('.news-cluster[data-category=economy] .map-story-title').first.click()
    page.wait_for_function("document.querySelector('#modal-body').textContent.length>100")
    page.keyboard.press('Escape');page.wait_for_timeout(300)
    assert page.locator('#article-modal').is_hidden()
    assert page.locator('#topic-map').get_attribute('data-camera')==before
    assert page.evaluate('({x:scrollX,y:scrollY,left:document.getElementById("topic-map").scrollLeft,top:document.getElementById("topic-map").scrollTop})')==scroll_before
    page.locator('.news-cluster[data-category=economy] .map-story-title').first.click()
    page.locator('#modal-close').click();page.wait_for_timeout(300)
    assert page.locator('#topic-map').get_attribute('data-camera')==before
    page.locator('.news-cluster[data-category=economy] .cluster-paging button').last.click()
    assert page.locator('.news-cluster[data-category=economy] .cluster-paging span').inner_text().startswith('2 /')
    assert page.locator('#topic-map').get_attribute('data-camera')==before
    rect=page.locator('#topic-map').bounding_box()
    page.mouse.move(rect['x']+20,rect['y']+20);page.mouse.down();page.mouse.move(rect['x']+100,rect['y']+80,steps=10);page.mouse.up()
    assert page.locator('#topic-map').get_attribute('data-camera')!=before
    assert page.locator('#article-modal').is_hidden()
    before=page.locator('#topic-map').get_attribute('data-camera');page.mouse.wheel(0,-100)
    page.wait_for_timeout(80)
    assert page.locator('#topic-map').get_attribute('data-camera')!=before
    camera_before=page.locator('#topic-map').get_attribute('data-camera')
    page.locator('#tab-news').click();page.locator('#tab-overview').click()
    assert page.locator('#topic-map').get_attribute('data-camera')==camera_before
    mobile=browser.new_context(viewport={'width':390,'height':844},is_mobile=True,has_touch=True)
    phone=mobile.new_page();phone.on('pageerror',lambda e:errors.append(str(e)))
    phone.goto(os.environ.get('NEWS_MAP_URL', 'http://127.0.0.1:8766/docs/index.html#overview'))
    phone.locator('#map-categories button[data-category=economy]').click()
    phone.locator('#topic-map').scroll_into_view_if_needed()
    phone.screenshot(path='.audit/map-mobile.png')
    assert phone.evaluate('document.documentElement.scrollWidth<=innerWidth')
    box=phone.locator('#topic-map').bounding_box();cy=box['y']+box['height']/2;cx=box['x']+box['width']/2
    before=phone.locator('#topic-map').get_attribute('data-camera')
    cdp=mobile.new_cdp_session(phone)
    cdp.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[{'x':cx-40,'y':cy,'id':1},{'x':cx+40,'y':cy,'id':2}]})
    cdp.send('Input.dispatchTouchEvent',{'type':'touchMove','touchPoints':[{'x':cx-75,'y':cy,'id':1},{'x':cx+75,'y':cy,'id':2}]})
    cdp.send('Input.dispatchTouchEvent',{'type':'touchEnd','touchPoints':[]})
    phone.wait_for_timeout(100)
    assert phone.locator('#topic-map').get_attribute('data-camera')!=before
    phone.locator('#map-categories button[data-category=economy]').click()
    phone.locator('#topic-map').scroll_into_view_if_needed()
    before=phone.locator('#topic-map').get_attribute('data-camera')
    phone.locator('.news-cluster[data-category=economy] .map-story-title').first.click()
    phone.locator('#modal-close-fixed').click();phone.wait_for_timeout(300)
    assert phone.locator('#article-modal').is_hidden()
    assert phone.locator('#topic-map').get_attribute('data-camera')==before
    assert not errors,errors
    result={'clusters':11,'summary_cards':page.locator('.map-story').count(),'esc_preserves_camera':True,'exit_preserves_camera':True,'category_paging':True,'drag':True,'wheel_zoom':True,'touch_pinch':True,'tab_preserves_camera':True,'mobile_exit_preserves_camera':True,'mobile_overflow':False,'js_errors':errors}
    print(json.dumps(result))
    Path('.audit/map-browser-result.json').write_text(json.dumps(result,indent=2))
    browser.close()
