"""
DOM 解析模块

负责 HTML 清洗与结构化，输出简化后的 PageSchema。
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Dict

from bs4 import BeautifulSoup, Tag
from ...utils.exceptions import PerceptionError


@dataclass
class PageElement:
    """
    页面交互元素
    """
    element_id: int
    type: str
    text: str
    interactable: bool
    role: str
    title: Optional[str] = None
    placeholder: Optional[str] = None
    attributes: Dict[str, str] = field(default_factory=dict)
    selector: Optional[str] = None  # 选择器（由 SoM 提取或计算生成）
    center_x: Optional[int] = None  # 元素中心 X 坐标
    center_y: Optional[int] = None  # 元素中心 Y 坐标

    def to_dict(self) -> Dict[str, Optional[object]]:
        return {
            "id": self.element_id,
            "element_id": self.element_id,
            "type": self.type,
            "text": self.text,
            "interactable": self.interactable,
            "role": self.role,
            "title": self.title,
            "placeholder": self.placeholder,
            "selector": self.selector,
            "center_x": self.center_x,
            "center_y": self.center_y,
        }


@dataclass
class PageSchema:
    """
    页面结构化结果
    """
    url: str = ""
    title: str = ""
    summary: str = ""
    page_type: str = "unknown"
    elements: List[PageElement] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return {
            "url": self.url,
            "title": self.title,
            "summary": self.summary,
            "page_type": self.page_type,
            "elements": [element.to_dict() for element in self.elements],
        }


class DOMParser:
    """
    DOM 结构解析器

    负责 HTML 清洗与交互元素提取。
    """

    INTERACTIVE_TAGS = {"button", "input", "a", "select", "textarea", "option"}
    CLICKABLE_ROLES = {"button", "link", "tab", "menuitem"}

    def __init__(self):
        # 【修复】不再在这里分配最终的element_id
        # element_id的最终分配由ElementRegistry负责（基于选择器持久化映射）
        # 这个计数器保留用于生成临时ID和向后兼容
        self._next_id = 1

    def clean_and_parse(self, html: str) -> PageSchema:
        """
        清洗 HTML 并解析为 PageSchema。

        Args:
            html: 原始页面 HTML

        Returns:
            PageSchema: 结构化页面信息

        Raises:
            PerceptionError: 解析失败时抛出
        """
        try:
            soup = BeautifulSoup(html, "html.parser")
            self._remove_irrelevant_tags(soup)
            page_schema = PageSchema()
            page_schema.title = self._extract_title(soup)
            page_schema.summary = self._extract_summary(soup)
            page_schema.elements = self._extract_interactive_elements(soup)
            page_schema.page_type = self._guess_page_type(page_schema)
            return page_schema
        except Exception as exc:
            raise PerceptionError(f"DOM 解析失败: {exc}")

    def _remove_irrelevant_tags(self, soup: BeautifulSoup) -> None:
        for name in ["script", "style", "svg", "noscript", "iframe", "canvas"]:
            for tag in soup.find_all(name):
                tag.decompose()

    def _extract_title(self, soup: BeautifulSoup) -> str:
        if soup.title and soup.title.string:
            return soup.title.string.strip()
        heading = soup.find(["h1", "h2"])
        return heading.get_text(" ", strip=True) if heading else ""

    def _extract_summary(self, soup: BeautifulSoup) -> str:
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc and meta_desc.get("content"):
            return meta_desc.get("content").strip()
        first_paragraph = soup.find("p")
        return first_paragraph.get_text(" ", strip=True) if first_paragraph else ""

    def _is_clickable_div_span(self, tag: Tag) -> bool:
        if tag.name not in {"div", "span"}:
            return False
        style = tag.get("style", "")
        if "cursor:pointer" in style.replace(" ", "").lower():
            return True
        if tag.has_attr("onclick"):
            return True
        role = tag.get("role", "").lower()
        if role in self.CLICKABLE_ROLES:
            return True
        return False

    def _extract_interactive_elements(self, soup: BeautifulSoup) -> List[PageElement]:
        raw_elements = []
        raw_elements.extend(soup.find_all(list(self.INTERACTIVE_TAGS)))
        raw_elements.extend([tag for tag in soup.find_all(["div", "span"]) if self._is_clickable_div_span(tag)])

        elements: List[PageElement] = []
        seen = set()

        for tag in raw_elements:
            if not isinstance(tag, Tag):
                continue
            identifier = self._normalize_tag(tag)
            if identifier in seen:
                continue
            seen.add(identifier)
            element = self._build_element(tag)
            if element.interactable:
                elements.append(element)

        return elements

    def _normalize_tag(self, tag: Tag) -> str:
        return f"{tag.name}-{tag.get('id','')}-{tag.get('class','')}-{tag.get_text(' ', strip=True)[:80]}"

    def _build_element(self, tag: Tag) -> PageElement:
        text = self._extract_text(tag)
        title = tag.get("title") or tag.get("aria-label") or ""
        placeholder = tag.get("placeholder") or ""
        role = self._guess_role(tag, text)
        attributes = {k: str(v) for k, v in tag.attrs.items() if k in {"id", "name", "type", "role", "aria-label", "placeholder", "title"}}

        # 【修复】暂时使用递增的临时ID
        # 后续由ElementRegistry基于选择器映射到持久化ID
        # 这样可以确保同一个DOM元素在不同perception调用中保持一致的ID
        element = PageElement(
            element_id=self._next_id,
            type=tag.name,
            text=text,
            interactable=True,
            role=role,
            title=title,
            placeholder=placeholder,
            attributes=attributes,
        )
        self._next_id += 1
        return element

    def _extract_text(self, tag: Tag) -> str:
        if tag.name == "input":
            return tag.get("value", tag.get("placeholder", "")).strip()
        if tag.name == "img":
            return tag.get("alt", "").strip()
        return tag.get_text(" ", strip=True)

    def _guess_role(self, tag: Tag, text: str) -> str:
        role = tag.get("role", "").lower()
        if role:
            return role
        if tag.name == "button" or tag.get("type") in {"button", "submit", "reset"}:
            return "button"
        if tag.name == "a":
            return "link"
        if tag.name == "input":
            input_type = tag.get("type", "text").lower()
            return input_type
        if tag.name in {"select", "textarea"}:
            return tag.name
        if self._is_clickable_div_span(tag):
            return "clickable"
        if "buy" in text.lower() or "购买" in text.lower() or "立即" in text.lower():
            return "button"
        return "unknown"

    def _guess_page_type(self, page_schema: PageSchema) -> str:
        button_texts = [element.text.lower() for element in page_schema.elements if element.role == "button"]
        if any(keyword in " ".join(button_texts) for keyword in ["购买", "立即购买", "checkout", "submit"]):
            return "product_form"
        return "unknown"
