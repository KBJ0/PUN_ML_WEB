// 비동기 API 요청을 위한 헬퍼 함수
async function api(path, options = {}) {
  const res = await fetch(path, {
    credentials: "same-origin", // 세션 쿠키 전송
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });

  if (!res.ok) {
    // 401 Unauthorized 에러 시 로그인 페이지로 리디렉션
    if (res.status === 401) {
      alert("로그인 후 이용하세요.");
      window.location.href = "/auth/login";
      throw new Error("401 Unauthorized");
    }
    // 그 외 에러는 메시지 표시
    const msg = await res.text();
    alert(msg || `요청 실패: ${res.status}`);
    throw new Error(msg || res.statusText);
  }

  // 204 No Content 응답 처리
  return res.status === 204 ? null : res.json();
}

// Todo 목록을 새로고침하는 함수
async function refreshTodos() {
  const list = document.querySelector("#list");
  if (!list) return; // #list 요소가 없으면 함수 종료

  try {
    const todos = await api("/api/todos");
    list.innerHTML = ""; // 목록 초기화
    todos.forEach((t) => {
      const li = document.createElement("li");
      li.dataset.id = t.id;
      li.className = t.is_done ? "done" : "";
      li.innerHTML = `
        <input type="checkbox" class="toggle" ${t.is_done ? "checked" : ""}/>
        <span class="title" contenteditable="true"></span>
        <button class="del">삭제</button>
      `;
      li.querySelector(".title").textContent = t.title;
      list.appendChild(li);
    });
  } catch (err) {
    console.error("Todo 목록을 불러오는 데 실패했습니다:", err);
  }
}

// 새 Todo 항목을 생성하는 함수
async function createTodoItem(e) {
  e.preventDefault();
  const input = document.querySelector("#new-title");
  if (!input) return;

  const title = input.value.trim();
  if (!title) return;

  await api("/api/todos", { method: "POST", body: JSON.stringify({ title }) });
  input.value = "";
  await refreshTodos();
}

// DOM이 완전히 로드된 후 이벤트 리스너를 설정
document.addEventListener("DOMContentLoaded", () => {
  // ToDoList 관련 요소가 있는 페이지에서만 이벤트 리스너를 등록합니다.
  const todoForm = document.querySelector("#new-form");
  if (todoForm) {
    todoForm.addEventListener("submit", (e) => createTodoItem(e).catch(console.error));

    // 이벤트 위임을 사용하여 목록 전체에 대한 이벤트 처리
    const listContainer = document.querySelector("#list");
    if(listContainer) {
        // 완료/미완료 토글
        listContainer.addEventListener("change", async (e) => {
            if (e.target.classList.contains("toggle")) {
                const li = e.target.closest("li");
                const id = li.dataset.id;
                const is_done = e.target.checked;
                try {
                    await api(`/api/todos/${id}`, { method: "PATCH", body: JSON.stringify({ is_done }) });
                    li.classList.toggle("done", is_done);
                } catch (err) {
                    console.error(err);
                    await refreshTodos(); // 실패 시 목록 원상 복구
                }
            }
        });

        // 삭제 버튼 클릭
        listContainer.addEventListener("click", async (e) => {
            if (e.target.classList.contains("del")) {
                const li = e.target.closest("li");
                const id = li.dataset.id;
                if (confirm("정말 삭제하시겠습니까?")) {
                    try {
                        await api(`/api/todos/${id}`, { method: "DELETE" });
                        li.remove();
                    } catch (err) {
                        console.error(err);
                        await refreshTodos();
                    }
                }
            }
        });

        // 제목 수정
        listContainer.addEventListener("blur", async (e) => {
            if (e.target.classList.contains("title")) {
                const li = e.target.closest("li");
                const id = li.dataset.id;
                const title = e.target.textContent.trim();
                if (title) {
                    try {
                        await api(`/api/todos/${id}`, { method: "PATCH", body: JSON.stringify({ title }) });
                    } catch (err) {
                        console.error(err);
                    }
                }
                // 수정 후에는 전체 목록을 새로고침하여 데이터 일관성을 맞춤
                await refreshTodos();
            }
        }, true); // blur 이벤트는 캡처링 단계에서 처리
    }

    // 페이지 로드 시 Todo 목록을 불러옵니다.
    refreshTodos().catch(console.error);
  }
});
