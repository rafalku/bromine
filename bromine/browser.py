import six

from selenium.webdriver.common.by import By
from selenium.common.exceptions import WebDriverException
import selenium.webdriver.common.keys
from selenium.webdriver.support.ui import Select, WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


class Browser:
    """
    A wrapper for a selenium driver to simplify interaction.
    """

    Keys = selenium.webdriver.common.keys.Keys
    exceptions = selenium.common.exceptions

    def __init__(self, driver):
        self._driver = driver
        self._wait = WebDriverWait(driver, 2, poll_frequency=0.1)

    def __getattr__(self, attr):
        return getattr(self._driver, attr)

    def elem(self, css=None, **kwargs):
        if css is not None:
            kwargs["css"] = css
        return FutureElement(self, kwargs)

    __call__ = elem

    def find(self, css=None, **kwargs):
        if css is not None:
            kwargs["css"] = css
        sel, val = self._get_selector(kwargs)
        return [ElemWrapper(i) for i in self._driver.find_elements(sel, val)]

    def wait(self, **kwargs):
        meth, args = self._get_condition(kwargs)
        return ElemWrapper(self._wait.until(meth(*args)))

    selectors = {
        "id": By.ID,
        "xpath": By.XPATH,
        "link": By.LINK_TEXT,
        "partial_link": By.PARTIAL_LINK_TEXT,
        "name": By.NAME,
        "tag": By.TAG_NAME,
        "cls": By.CLASS_NAME,
        "css": By.CSS_SELECTOR,
    }

    @classmethod
    def _get_selector(cls, kwargs, selectors=None):
        if selectors is None:
            selectors = cls.selectors

        for k in kwargs:
            if k not in selectors:
                raise TypeError("bad selector: %s" % k)
        if not kwargs:
            raise TypeError("no selector specified")
        elif len(kwargs) > 1:
            raise TypeError("only one selector, please")

        sel, val = list(kwargs.items())[0]
        sel = selectors[sel]
        return sel, val

    conditions = {"title_has": EC.title_contains, "title": EC.title_is}

    @classmethod
    def _get_condition(cls, kwargs):
        for k in kwargs:
            if k not in cls.conditions:
                raise TypeError("bad wait condition: %s" % k)
        if len(kwargs) > 1:
            raise TypeError("only one condition, please")
        elif not kwargs:
            raise TypeError("no condition specified")

        cond, val = list(kwargs.items())[0]
        cond = cls.conditions[cond]
        return cond, [val]


class FutureElement:
    def __init__(self, browser, kwargs):
        self._browser = browser
        self._kwargs = kwargs
        self._elem = None

    def wait(self, condition="present", arg=None):
        neg = False
        if condition.split(None, 1)[0] == "not":
            neg = True
            condition = condition[3:].lstrip()

        if not condition:
            condition = "present"

        if condition == "present":
            meth = EC.presence_of_element_located
        elif condition == "clickable":
            meth = EC.element_to_be_clickable
        elif condition == "visible":
            meth = EC.visibility_of_element_located
        elif condition == "text":
            meth = element_containing_text
        else:
            raise TypeError("bad condition: %s" % condition)

        sel, val = self._browser._get_selector(self._kwargs)
        wait = self._browser._wait
        wmeth = wait.until if not neg else wait.until_not
        args = [(sel, val)]
        if arg is not None:
            args.append(arg)
        try:
            self._elem = ElemWrapper(wmeth(meth(*args)))
        except WebDriverException as e:
            do_raise(
                type(e)(
                    "error waiting for '%s' to be %s%s%s: %s %s"
                    % (
                        ", ".join(
                            "%s: %s" % p for p in sorted(self._kwargs.items())
                        ),
                        neg and "not " or "",
                        condition,
                        " (%s)" % arg if arg is not None else "",
                        e.__class__.__name__,
                        e,
                    )
                )
            )

        return self._elem

    def __getattr__(self, attr):
        if self._elem is None:
            sel, val = self._browser._get_selector(self._kwargs)
            try:
                self._elem = ElemWrapper(self._browser.find_element(sel, val))
            except WebDriverException as e:
                do_raise(e)

        return getattr(self._elem, attr)

    # Methods always requiring some sort of wait to be useful

    def clear(self):
        elem = self.wait("clickable")
        return elem.clear()

    def click(self):
        elem = self.wait("clickable")
        return elem.click()

    def send_keys(self, *args):
        elem = self.wait("clickable")
        return elem.send_keys(*args)

    def select(self, **kwargs):
        elem = self.wait("clickable")
        return elem.select(**kwargs)


class ElemWrapper:
    def __init__(self, elem):
        self._elem = elem

    def elem(self, css=None, **kwargs):
        if css is not None:
            kwargs["css"] = css
        sel, val = Browser._get_selector(kwargs)
        try:
            return ElemWrapper(self._elem.find_element(sel, val))
        except WebDriverException as e:
            do_raise(e)

    __call__ = elem

    def find(self, css=None, **kwargs):
        if css is not None:
            kwargs["css"] = css
        sel, val = Browser._get_selector(kwargs)
        return [ElemWrapper(i) for i in self._elem.find_elements(sel, val)]

    def select(self, **kwargs):
        """Pick an item of a SELECT element according to a certain property"""
        sel, val = Browser._get_selector(kwargs, self._select_selectors)
        return sel(Select(self._elem), val)

    _select_selectors = {
        "index": Select.select_by_index,
        "text": Select.select_by_visible_text,
        "value": Select.select_by_value,
    }

    def clear(self):
        """Like the upstream clear, but return the element itself for chaining

        e.g. input.clear().send_keys("...")
        """
        self._elem.clear()
        return self

    def __getattr__(self, attr):
        return getattr(self._elem, attr)

    def __repr__(self):
        s = repr(self._elem)
        return "<wrapped " + s[1:]


class element_containing_text:
    """An expectation for checking if text is present in the specified element.

    Unlike `EC.text_to_be_present_in_element` return the element, not True,
    thank you.

    Text can be 'none', meaning "any text". As soon as we need it, it may be
    a regexp pattern too.
    """

    def __init__(self, locator, text_=None):
        self.locator = locator
        self.text = text_

    def __call__(self, driver):
        try:
            elem = EC._find_element(driver, self.locator)
            if self.text is None:
                if elem.text:
                    return elem
            else:
                if self.text in elem.text:
                    return elem
        except EC.StaleElementReferenceException:
            pass

        return False


# Hack to shorten traceback in py.test
def do_raise(e):
    if six.PY3:
        raise e.with_traceback(None)
    else:
        raise e
