import { importShared } from './__federation_fn_import-JrT3xvdd.js';

const {createElementVNode:_createElementVNode,resolveComponent:_resolveComponent,createVNode:_createVNode,withCtx:_withCtx,toDisplayString:_toDisplayString,createTextVNode:_createTextVNode,openBlock:_openBlock,createBlock:_createBlock,createCommentVNode:_createCommentVNode,createElementBlock:_createElementBlock} = await importShared('vue');


const _hoisted_1 = { class: "autosubrename-page pa-4" };

const {onMounted,ref} = await importShared('vue');



const _sfc_main = {
  __name: 'Page',
  props: {
  api: {
    type: Object,
    default: () => ({}),
  },
  initialConfig: {
    type: Object,
    default: null,
  },
},
  emits: ['save', 'close'],
  setup(__props, { emit: __emit }) {

const props = __props;

const emit = __emit;

const loading = ref(true);
const saving = ref(false);
const error = ref('');
const savedMessage = ref('');
const config = ref({
  enabled: false,
  notify: false,
  onlyonce: false,
  clear_cache: false,
  monitor_dirs: '',
  video_exts: 'mp4,mkv,avi,ts',
  sub_exts: 'ass,ssa,srt,sup',
});

async function loadConfig() {
  loading.value = true;
  error.value = '';
  try {
    if (props.initialConfig && Object.keys(props.initialConfig).length > 0) {
      config.value = { ...config.value, ...props.initialConfig, clear_cache: false };
      return
    }
    const result = await props.api.get('plugin/form/AutoSubRename');
    if (result?.model) {
      config.value = { ...config.value, ...result.model, clear_cache: false };
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

async function saveConfig() {
  saving.value = true;
  error.value = '';
  savedMessage.value = '';
  try {
    const payload = { ...config.value };
    if (props.initialConfig && Object.keys(props.initialConfig).length > 0) {
      emit('save', payload);
      config.value.clear_cache = false;
      savedMessage.value = '设置已保存';
      return
    }
    const result = await props.api.put('plugin/AutoSubRename', payload);
    if (!result?.success) {
      throw new Error(result?.message || '保存设置失败')
    }
    config.value.clear_cache = false;
    savedMessage.value = '设置已保存';
    await loadConfig();
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    saving.value = false;
  }
}

async function clearCache() {
  config.value.clear_cache = true;
  await saveConfig();
}

onMounted(loadConfig);

return (_ctx, _cache) => {
  const _component_VSpacer = _resolveComponent("VSpacer");
  const _component_VBtn = _resolveComponent("VBtn");
  const _component_VToolbar = _resolveComponent("VToolbar");
  const _component_VDivider = _resolveComponent("VDivider");
  const _component_VAlert = _resolveComponent("VAlert");
  const _component_VSwitch = _resolveComponent("VSwitch");
  const _component_VCol = _resolveComponent("VCol");
  const _component_VRow = _resolveComponent("VRow");
  const _component_VTextarea = _resolveComponent("VTextarea");
  const _component_VTextField = _resolveComponent("VTextField");

  return (_openBlock(), _createElementBlock("div", _hoisted_1, [
    _createVNode(_component_VToolbar, {
      density: "comfortable",
      color: "transparent"
    }, {
      default: _withCtx(() => [
        _cache[9] || (_cache[9] = _createElementVNode("div", { class: "text-h6" }, "剧集字幕重命名设置", -1)),
        _createVNode(_component_VSpacer),
        _createVNode(_component_VBtn, {
          icon: "mdi-refresh",
          variant: "text",
          loading: loading.value,
          onClick: loadConfig
        }, null, 8, ["loading"]),
        _createVNode(_component_VBtn, {
          icon: "mdi-content-save",
          variant: "text",
          color: "primary",
          loading: saving.value,
          onClick: saveConfig
        }, null, 8, ["loading"]),
        _createVNode(_component_VBtn, {
          icon: "mdi-close",
          variant: "text",
          onClick: _cache[0] || (_cache[0] = $event => (emit('close')))
        })
      ]),
      _: 1
    }),
    _createVNode(_component_VDivider, { class: "mb-4" }),
    (error.value)
      ? (_openBlock(), _createBlock(_component_VAlert, {
          key: 0,
          type: "error",
          variant: "tonal",
          class: "mb-4"
        }, {
          default: _withCtx(() => [
            _createTextVNode(_toDisplayString(error.value), 1)
          ]),
          _: 1
        }))
      : _createCommentVNode("", true),
    (savedMessage.value)
      ? (_openBlock(), _createBlock(_component_VAlert, {
          key: 1,
          type: "success",
          variant: "tonal",
          class: "mb-4"
        }, {
          default: _withCtx(() => [
            _createTextVNode(_toDisplayString(savedMessage.value), 1)
          ]),
          _: 1
        }))
      : _createCommentVNode("", true),
    _createVNode(_component_VRow, null, {
      default: _withCtx(() => [
        _createVNode(_component_VCol, {
          cols: "12",
          md: "3"
        }, {
          default: _withCtx(() => [
            _createVNode(_component_VSwitch, {
              modelValue: config.value.enabled,
              "onUpdate:modelValue": _cache[1] || (_cache[1] = $event => ((config.value.enabled) = $event)),
              label: "启用插件",
              disabled: loading.value || saving.value
            }, null, 8, ["modelValue", "disabled"])
          ]),
          _: 1
        }),
        _createVNode(_component_VCol, {
          cols: "12",
          md: "3"
        }, {
          default: _withCtx(() => [
            _createVNode(_component_VSwitch, {
              modelValue: config.value.notify,
              "onUpdate:modelValue": _cache[2] || (_cache[2] = $event => ((config.value.notify) = $event)),
              label: "发送通知",
              disabled: loading.value || saving.value
            }, null, 8, ["modelValue", "disabled"])
          ]),
          _: 1
        }),
        _createVNode(_component_VCol, {
          cols: "12",
          md: "3"
        }, {
          default: _withCtx(() => [
            _createVNode(_component_VSwitch, {
              modelValue: config.value.onlyonce,
              "onUpdate:modelValue": _cache[3] || (_cache[3] = $event => ((config.value.onlyonce) = $event)),
              label: "立即运行一次",
              disabled: loading.value || saving.value
            }, null, 8, ["modelValue", "disabled"])
          ]),
          _: 1
        }),
        _createVNode(_component_VCol, {
          cols: "12",
          md: "3"
        }, {
          default: _withCtx(() => [
            _createVNode(_component_VSwitch, {
              modelValue: config.value.clear_cache,
              "onUpdate:modelValue": [
                _cache[4] || (_cache[4] = $event => ((config.value.clear_cache) = $event)),
                _cache[5] || (_cache[5] = value => value && clearCache())
              ],
              label: "一键清除重命名记录缓存",
              disabled: loading.value || saving.value
            }, null, 8, ["modelValue", "disabled"])
          ]),
          _: 1
        })
      ]),
      _: 1
    }),
    _createVNode(_component_VTextarea, {
      modelValue: config.value.monitor_dirs,
      "onUpdate:modelValue": _cache[6] || (_cache[6] = $event => ((config.value.monitor_dirs) = $event)),
      label: "监控目录",
      rows: "3",
      placeholder: "每行一个目录路径（支持子目录监控）",
      disabled: loading.value || saving.value,
      class: "mb-4"
    }, null, 8, ["modelValue", "disabled"]),
    _createVNode(_component_VRow, null, {
      default: _withCtx(() => [
        _createVNode(_component_VCol, {
          cols: "12",
          md: "6"
        }, {
          default: _withCtx(() => [
            _createVNode(_component_VTextField, {
              modelValue: config.value.video_exts,
              "onUpdate:modelValue": _cache[7] || (_cache[7] = $event => ((config.value.video_exts) = $event)),
              label: "视频扩展名",
              placeholder: "多个用逗号分隔",
              disabled: loading.value || saving.value
            }, null, 8, ["modelValue", "disabled"])
          ]),
          _: 1
        }),
        _createVNode(_component_VCol, {
          cols: "12",
          md: "6"
        }, {
          default: _withCtx(() => [
            _createVNode(_component_VTextField, {
              modelValue: config.value.sub_exts,
              "onUpdate:modelValue": _cache[8] || (_cache[8] = $event => ((config.value.sub_exts) = $event)),
              label: "字幕扩展名",
              placeholder: "多个用逗号分隔，例如 ass,ssa,srt,sup",
              disabled: loading.value || saving.value
            }, null, 8, ["modelValue", "disabled"])
          ]),
          _: 1
        })
      ]),
      _: 1
    }),
    _createVNode(_component_VAlert, {
      type: "info",
      variant: "tonal",
      class: "mt-4"
    }, {
      default: _withCtx(() => [...(_cache[10] || (_cache[10] = [
        _createTextVNode(" 设置会直接保存到 MoviePilot；清除缓存只清除已处理路径记录，不会删除任何视频或字幕文件。 ", -1)
      ]))]),
      _: 1
    })
  ]))
}
}

};

export { _sfc_main as default };
