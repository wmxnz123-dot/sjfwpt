(function () {
  "use strict";

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function renderInline(text) {
    var html = escapeHtml(text);
    html = html.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, function (_match, alt, src) {
      if (!isSafeImageUrl(src)) return _match;
      return '<img class="pa-markdown-image" src="' + src + '" alt="' + alt + '" loading="lazy">';
    });
    html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
    html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    html = html.replace(/\*([^*]+)\*/g, "<em>$1</em>");
    html = html.replace(/==([^=]+)==/g, "<mark>$1</mark>");
    html = html.replace(/\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer">$1</a>');
    return html;
  }

  function isSafeImageUrl(src) {
    src = String(src || "").trim();
    if (!src || /[\s"'<>]/.test(src)) return false;
    if (/^https?:\/\/[^\s"'<>]+$/i.test(src)) return true;
    if (/^\/\.prototype-annotations\/assets\/[a-zA-Z0-9._/-]+$/.test(src)) return true;
    if (/^\.\/\.prototype-annotations\/assets\/[a-zA-Z0-9._/-]+$/.test(src)) return true;
    if (/^\.prototype-annotations\/assets\/[a-zA-Z0-9._/-]+$/.test(src)) return true;
    if (/^\/prototype-annotator\/assets\/[a-zA-Z0-9._/-]+$/.test(src)) return true;
    if (/^\.\/prototype-annotator\/assets\/[a-zA-Z0-9._/-]+$/.test(src)) return true;
    if (/^prototype-annotator\/assets\/[a-zA-Z0-9._/-]+$/.test(src)) return true;
    return false;
  }

  function isTableStart(lines, index) {
    return index + 1 < lines.length &&
      /^\s*\|.+\|\s*$/.test(lines[index]) &&
      /^\s*\|?[\s:-]+\|[\s|:-]*\|?\s*$/.test(lines[index + 1]);
  }

  function splitTableRow(line) {
    return line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map(function (cell) {
      return cell.trim();
    });
  }

  function renderTable(lines, start) {
    var header = splitTableRow(lines[start]);
    var rows = [];
    var index = start + 2;
    while (index < lines.length && /^\s*\|.+\|\s*$/.test(lines[index])) {
      rows.push(splitTableRow(lines[index]));
      index += 1;
    }
    var html = "<table><thead><tr>" + header.map(function (cell) {
      return "<th>" + renderInline(cell) + "</th>";
    }).join("") + "</tr></thead><tbody>";
    rows.forEach(function (row) {
      html += "<tr>" + row.map(function (cell) {
        return "<td>" + renderInline(cell) + "</td>";
      }).join("") + "</tr>";
    });
    html += "</tbody></table>";
    return { html: html, next: index };
  }

  function renderMarkdown(markdown) {
    var lines = String(markdown || "").replace(/\r\n/g, "\n").split("\n");
    var html = "";
    var paragraph = [];
    var listType = null;
    var inCode = false;
    var codeLang = "";
    var codeLines = [];

    function flushParagraph() {
      if (!paragraph.length) return;
      html += "<p>" + renderInline(paragraph.join(" ")) + "</p>";
      paragraph = [];
    }

    function closeList() {
      if (!listType) return;
      html += "</" + listType + ">";
      listType = null;
    }

    function flushCode() {
      var code = codeLines.join("\n");
      if (codeLang.toLowerCase() === "mermaid") {
        html += '<div class="pa-mermaid" data-pa-mermaid>' + escapeHtml(code) + "</div>";
      } else {
        html += "<pre><code>" + escapeHtml(code) + "</code></pre>";
      }
      inCode = false;
      codeLang = "";
      codeLines = [];
    }

    for (var i = 0; i < lines.length; i += 1) {
      var line = lines[i];

      if (/^```/.test(line.trim())) {
        if (inCode) {
          flushCode();
        } else {
          flushParagraph();
          closeList();
          inCode = true;
          codeLang = line.trim().replace(/^```/, "").trim();
          codeLines = [];
        }
        continue;
      }

      if (inCode) {
        codeLines.push(line);
        continue;
      }

      if (!line.trim()) {
        flushParagraph();
        closeList();
        continue;
      }

      if (isTableStart(lines, i)) {
        flushParagraph();
        closeList();
        var table = renderTable(lines, i);
        html += table.html;
        i = table.next - 1;
        continue;
      }

      var heading = /^(#{1,4})\s+(.+)$/.exec(line);
      if (heading) {
        flushParagraph();
        closeList();
        var level = heading[1].length;
        html += "<h" + level + ">" + renderInline(heading[2]) + "</h" + level + ">";
        continue;
      }

      var quote = /^>\s+(.+)$/.exec(line);
      if (quote) {
        flushParagraph();
        closeList();
        html += "<blockquote>" + renderInline(quote[1]) + "</blockquote>";
        continue;
      }

      var bullet = /^\s*[-*]\s+(.+)$/.exec(line);
      var numbered = /^\s*\d+\.\s+(.+)$/.exec(line);
      if (bullet || numbered) {
        flushParagraph();
        var nextType = bullet ? "ul" : "ol";
        if (listType !== nextType) {
          closeList();
          listType = nextType;
          html += "<" + listType + ">";
        }
        html += "<li>" + renderInline((bullet || numbered)[1]) + "</li>";
        continue;
      }

      paragraph.push(line.trim());
    }

    if (inCode) flushCode();
    flushParagraph();
    closeList();
    return html || "<p></p>";
  }

  window.PrototypeAnnotatorMarkdown = {
    escapeHtml: escapeHtml,
    render: renderMarkdown
  };
})();
