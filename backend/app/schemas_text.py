from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TextInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


FunctionName = Annotated[str, Field(pattern=r"^[A-Za-z_][A-Za-z0-9_-]{0,63}$")]
ToolMode = Literal["auto", "none", "required"]


class FunctionDefinition(TextInput):
    name: FunctionName
    description: str | None = None
    parameters: dict | None = None
    strict: bool | None = None


class ChatTool(TextInput):
    type: Literal["function"]
    function: FunctionDefinition


class ChatFunctionChoice(TextInput):
    name: FunctionName


class ChatToolChoice(TextInput):
    type: Literal["function"]
    function: ChatFunctionChoice


class FunctionInvocation(TextInput):
    name: FunctionName
    arguments: str


class ChatToolCall(TextInput):
    id: str
    type: Literal["function"]
    function: FunctionInvocation


class TextPart(TextInput):
    type: Literal["text"]
    text: str


class ImageURL(TextInput):
    url: str
    detail: Literal["auto", "low", "high"] = "auto"


class ImagePart(TextInput):
    type: Literal["image_url"]
    image_url: ImageURL


class URLCitation(TextInput):
    url: str
    title: str
    start_index: int
    end_index: int


class ChatCitation(TextInput):
    type: Literal["url_citation"]
    url_citation: URLCitation


class ResponseCitation(URLCitation):
    type: Literal["url_citation"]


class ChatMessage(TextInput):
    role: Literal["system", "developer", "user", "assistant", "tool"]
    content: str | list[Annotated[TextPart | ImagePart, Field(discriminator="type")]] | None = None
    tool_calls: list[ChatToolCall] | None = None
    tool_call_id: str | None = None
    annotations: list[ChatCitation] | None = None
    refusal: str | None = None

    @model_validator(mode="after")
    def validate_tool_message(self):
        if self.role == "tool":
            if (
                not self.tool_call_id
                or self.tool_calls is not None
                or not isinstance(self.content, str)
            ):
                raise ValueError("Tool messages require tool_call_id and string content.")
        elif (
            self.tool_call_id is not None
            or (self.role != "assistant" and self.tool_calls is not None)
            or (self.content is None and not self.tool_calls)
        ):
            raise ValueError("Invalid message content or tool fields.")
        return self


class StreamOptions(TextInput):
    include_usage: bool = False


class WebSearchOptions(TextInput):
    pass


class JSONSchemaFormat(TextInput):
    name: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    description: str | None = None
    schema_: dict = Field(alias="schema")
    strict: bool = True


class ChatResponseFormat(TextInput):
    type: Literal["text", "json_object", "json_schema"]
    json_schema: JSONSchemaFormat | None = None

    @model_validator(mode="after")
    def validate_schema(self):
        if (self.type == "json_schema") != (self.json_schema is not None):
            raise ValueError("json_schema is required only for the json_schema format.")
        return self


class ChatRequest(TextInput):
    model: str = Field(min_length=1, max_length=160)
    messages: list[ChatMessage] = Field(min_length=1)
    stream: bool = False
    stream_options: StreamOptions | None = None
    max_completion_tokens: int | None = Field(default=None, gt=0, strict=True)
    n: Literal[1] = 1
    tools: list[ChatTool] = Field(default_factory=list)
    tool_choice: ToolMode | ChatToolChoice | None = None
    web_search_options: WebSearchOptions | None = None
    response_format: ChatResponseFormat | None = None


class ResponseTextPart(TextInput):
    type: Literal["input_text", "output_text"]
    text: str
    annotations: list[ResponseCitation] | None = None


class ResponseImagePart(TextInput):
    type: Literal["input_image"]
    image_url: str
    detail: Literal["auto", "low", "high"] = "auto"


class ResponseMessage(TextInput):
    type: Literal["message"] = "message"
    role: Literal["system", "developer", "user", "assistant"]
    id: str | None = None
    status: Literal["in_progress", "completed", "incomplete"] | None = None
    phase: Literal["commentary", "final_answer"] | None = None
    content: (
        str
        | list[
            Annotated[
                ResponseTextPart | ResponseImagePart,
                Field(discriminator="type"),
            ]
        ]
    )


class ResponseTool(FunctionDefinition):
    type: Literal["function"]


class ResponseWebSearch(TextInput):
    type: Literal["web_search"]


class ResponseToolChoice(TextInput):
    type: Literal["function"]
    name: FunctionName


class ResponseFunctionCall(FunctionInvocation):
    type: Literal["function_call"]
    call_id: str
    id: str | None = None
    status: Literal["in_progress", "completed", "incomplete"] | None = None


class ResponseFunctionOutput(TextInput):
    type: Literal["function_call_output"]
    call_id: str
    output: str


class ReasoningSummary(TextInput):
    type: Literal["summary_text"]
    text: str


class ResponseReasoning(TextInput):
    type: Literal["reasoning"]
    id: str
    summary: list[ReasoningSummary]
    encrypted_content: str | None = None
    status: Literal["in_progress", "completed", "incomplete"] | None = None


class ResponseFormat(JSONSchemaFormat):
    type: Literal["json_schema"]


class PlainResponseFormat(TextInput):
    type: Literal["text", "json_object"]


class ResponseTextConfig(TextInput):
    format: Annotated[ResponseFormat | PlainResponseFormat, Field(discriminator="type")]


class ResponsesRequest(TextInput):
    model: str = Field(min_length=1, max_length=160)
    input: (
        str
        | list[ResponseMessage | ResponseFunctionCall | ResponseFunctionOutput | ResponseReasoning]
    )
    instructions: str | None = None
    stream: bool = False
    max_output_tokens: int | None = Field(default=None, gt=0, strict=True)
    store: Literal[False] = False
    tools: list[Annotated[ResponseTool | ResponseWebSearch, Field(discriminator="type")]] = Field(
        default_factory=list
    )
    tool_choice: ToolMode | ResponseToolChoice | None = None
    text: ResponseTextConfig | None = None
    include: list[Literal["reasoning.encrypted_content"]] = Field(default_factory=list)


def web_search_requested(payload: ChatRequest | ResponsesRequest) -> bool:
    if isinstance(payload, ChatRequest):
        return payload.web_search_options is not None
    return any(isinstance(tool, ResponseWebSearch) for tool in payload.tools)
