import random
from os import path as osp

import magnum as mn
import numpy as np

import examples.settings
import habitat_sim


def test_no_navmesh_smoke():
    sim_cfg = habitat_sim.SimulatorConfiguration()
    agent_config = habitat_sim.AgentConfiguration()
    # No sensors as we are only testing to see if things work
    # with no navmesh and the navmesh isn't used for any exisitng sensors
    agent_config.sensor_specifications = []

    sim_cfg.scene_id = "data/test_assets/scenes/stage_floor1.glb"

    with habitat_sim.Simulator(
        habitat_sim.Configuration(sim_cfg, [agent_config])
    ) as sim:
        sim.initialize_agent(0)

        random.seed(0)
        for _ in range(50):
            obs = sim.step(random.choice(list(agent_config.action_space.keys())))
            # Can't collide with no navmesh
            assert not obs["collided"]


def test_empty_scene():
    cfg_settings = examples.settings.default_sim_settings.copy()

    # keyword "NONE" initializes a scene with no scene mesh
    cfg_settings["scene"] = "NONE"
    # test that depth sensor doesn't mind an empty scene
    cfg_settings["depth_sensor"] = True

    hab_cfg = examples.settings.make_cfg(cfg_settings)
    with habitat_sim.Simulator(hab_cfg) as sim:
        assert sim.get_stage_initialization_template() == None

        # test that empty frames can be rendered without a scene mesh
        for _ in range(2):
            sim.step(random.choice(list(hab_cfg.agents[0].action_space.keys())))


def test_sim_reset(make_cfg_settings):
    with habitat_sim.Simulator(examples.settings.make_cfg(make_cfg_settings)) as sim:
        agent_config = sim.config.agents[0]
        sim.initialize_agent(0)
        initial_state = sim.agents[0].initial_state
        # Take random steps in the environment
        for _ in range(10):
            action = random.choice(list(agent_config.action_space.keys()))
            sim.step(action)

        sim.reset()
        new_state = sim.agents[0].get_state()
        same_position = all(initial_state.position == new_state.position)
        same_rotation = np.isclose(
            initial_state.rotation, new_state.rotation, rtol=1e-4
        )  # Numerical error can cause slight deviations
        assert same_position and same_rotation


# Make sure you can keep a reference to an agent alive without crashing
def test_keep_agent():
    sim_cfg = habitat_sim.SimulatorConfiguration()
    agent_config = habitat_sim.AgentConfiguration()

    sim_cfg.scene_id = "data/scene_datasets/habitat-test-scenes/van-gogh-room.glb"
    agents = []

    for _ in range(3):
        with habitat_sim.Simulator(
            habitat_sim.Configuration(sim_cfg, [agent_config])
        ) as sim:
            agents.append(sim.get_agent(0))


# Make sure you can construct and destruct the simulator multiple times
def test_multiple_construct_destroy():
    sim_cfg = habitat_sim.SimulatorConfiguration()
    agent_config = habitat_sim.AgentConfiguration()

    sim_cfg.scene_id = "data/scene_datasets/habitat-test-scenes/van-gogh-room.glb"

    for _ in range(3):
        with habitat_sim.Simulator(habitat_sim.Configuration(sim_cfg, [agent_config])):
            pass


def test_scene_bounding_boxes():
    cfg_settings = examples.settings.default_sim_settings.copy()
    cfg_settings["scene"] = "data/scene_datasets/habitat-test-scenes/van-gogh-room.glb"
    hab_cfg = examples.settings.make_cfg(cfg_settings)
    with habitat_sim.Simulator(hab_cfg) as sim:
        scene_graph = sim.get_active_scene_graph()
        root_node = scene_graph.get_root_node()
        root_node.compute_cumulative_bb()
        scene_bb = root_node.cumulative_bb
        ground_truth = mn.Range3D.from_size(
            mn.Vector3(-0.775869, -0.0233012, -1.6706),
            mn.Vector3(6.76937, 3.86304, 3.5359),
        )
        assert ground_truth == scene_bb


def test_object_template_editing():
    cfg_settings = examples.settings.default_sim_settings.copy()
    cfg_settings["scene"] = "data/scene_datasets/habitat-test-scenes/van-gogh-room.glb"
    cfg_settings["enable_physics"] = True
    hab_cfg = examples.settings.make_cfg(cfg_settings)
    with habitat_sim.Simulator(hab_cfg) as sim:
        # test creating a new template with a test asset
        transform_box_path = osp.abspath("data/test_assets/objects/transform_box.glb")
        transform_box_template = habitat_sim.attributes.ObjectAttributes()
        transform_box_template.render_asset_handle = transform_box_path
        obj_mgr = sim.get_object_template_manager()
        old_library_size = obj_mgr.get_num_templates()
        transform_box_template_id = obj_mgr.register_template(
            transform_box_template, "transform_box_template"
        )
        assert obj_mgr.get_num_templates() > old_library_size
        assert transform_box_template_id != -1

        # test loading a test asset template from file
        sphere_path = osp.abspath("data/test_assets/objects/sphere")
        old_library_size = obj_mgr.get_num_templates()
        template_ids = obj_mgr.load_configs(sphere_path)
        assert len(template_ids) > 0
        assert obj_mgr.get_num_templates() > old_library_size

        # test getting and editing template reference - changes underlying template
        sphere_template = obj_mgr.get_template_by_ID(template_ids[0])
        assert sphere_template.render_asset_handle.endswith("sphere.glb")
        sphere_scale = np.array([2.0, 2.0, 2.0])
        sphere_template.scale = sphere_scale
        obj_mgr.register_template(sphere_template, sphere_template.handle)
        sphere_template2 = obj_mgr.get_template_by_ID(template_ids[0])
        assert sphere_template2.scale == sphere_scale

        # test adding a new object
        object_id = sim.add_object(template_ids[0])
        assert object_id != -1

        # test getting initialization templates
        stage_init_template = sim.get_stage_initialization_template()
        assert stage_init_template.render_asset_handle == cfg_settings["scene"]

        obj_init_template = sim.get_object_initialization_template(object_id)
        assert obj_init_template.render_asset_handle.endswith("sphere.glb")
